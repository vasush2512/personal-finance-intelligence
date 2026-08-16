"""Downloading the data as CSV or Excel (Phase 4).

Both formats come from libraries already in the project — csv from the standard
library, openpyxl because the uploader already reads .xlsx — so exporting adds
no dependency.

These are the only endpoints that return a file rather than JSON, and the only
place this data leaves the application. That is why the description column is
masked on the way out; see s12d_export for what and why.
"""

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.s16a_auth import current_user
from app.core.s04_models import Transaction, Upload, User
from app.routers.s18_transactions import MAX_LIMIT, build_filters
from app.store.s11c_tags import transaction_ids_with_tag
from app.store import s12_aggregations as aggregations
from app.store.s12d_export import (
    TRANSACTION_HEADERS,
    filename,
    summary_sheets,
    to_csv,
    to_excel,
    transaction_rows,
)

router = APIRouter(prefix="/api/export", tags=["export"])

# A ceiling on one download. Well above a normal statement year, and far below
# what would hold a hundred thousand rows in memory as a workbook.
EXPORT_LIMIT = 50_000

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _check_format(fmt: str) -> str:
    if fmt not in CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"format must be 'csv' or 'xlsx', got {fmt!r}.",
        )
    return fmt


def _as_download(body: bytes, name: str, fmt: str) -> Response:
    """Send bytes as a file the browser saves rather than renders."""
    return Response(
        content=body,
        media_type=CONTENT_TYPES[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            # The frontend reads the filename off the response rather than
            # rebuilding it, and a cross-origin fetch cannot see this header
            # unless it is explicitly exposed.
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/transactions")
def export_transactions(
    format: str = Query("csv", description="csv or xlsx"),
    month: str | None = Query(None, description="YYYY-MM"),
    category: str | None = Query(None),
    search: str | None = Query(None),
    direction: str | None = Query(None),
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    tag: str | None = Query(None),
    date_from: dt.date | None = Query(None),
    date_to: dt.date | None = Query(None),
    min_amount: Decimal | None = Query(None, ge=0),
    max_amount: Decimal | None = Query(None, ge=0),
    payment_method: str | None = Query(None),
    limit: int = Query(EXPORT_LIMIT, ge=1, le=EXPORT_LIMIT),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """The transaction list, filtered exactly as the table filters it.

    Same `build_filters` the table uses, so what downloads is what was on
    screen — an export that quietly ignores the active filter is the fastest
    way to make someone distrust both.
    """
    _check_format(format)
    conditions = build_filters(
        month, category, search, direction, upload_id, sheet,
        user_id=user.id, account_id=account_id,
        entry_source=entry_source,
    )

    rows = session.execute(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
    ).scalars().all()

    upload_names = dict(
        session.execute(
            select(Upload.id, Upload.filename).where(Upload.user_id == user.id)
        ).all()
    )
    table = transaction_rows(rows, upload_names)

    if format == "csv":
        body = to_csv(TRANSACTION_HEADERS, table)
    else:
        body = to_excel([("Transactions", TRANSACTION_HEADERS, table)])

    return _as_download(body, filename("transactions", format), format)


@router.get("/summary")
def export_summary(
    format: str = Query("csv"),
    month: str | None = Query(None, description="YYYY-MM"),
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Category totals, monthly trends and top merchants.

    As CSV this is the category breakdown only — a CSV file holds one table,
    and inventing a layout that stacks three would produce something no
    spreadsheet reads back correctly. The Excel version has all three as
    separate sheets.
    """
    _check_format(format)
    source = {"upload_id": upload_id, "sheet": sheet, "user_id": user.id,
              "account_id": account_id,
              "entry_source": entry_source}

    summary = aggregations.summary(session, month, **source)
    trends = aggregations.monthly_trends(session, **source)
    sheets = summary_sheets(summary, trends)

    if format == "csv":
        title, headers, rows = sheets[0]
        body = to_csv(headers, rows)
    else:
        body = to_excel(sheets)

    return _as_download(body, filename("summary", format), format)
