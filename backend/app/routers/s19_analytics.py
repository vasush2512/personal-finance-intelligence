"""GET /api/summary and GET /api/trends — the dashboard's numbers."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import FinancialHealth, Summary, TrendPoint, UploadSource
from app.store import s12_aggregations as aggregations
from app.store.s12a_health import financial_health
from app.store.s14_anomaly_service import find_anomalies
from app.store.s15c_settings import sensitivity_for

router = APIRouter(prefix="/api", tags=["analytics"])


def validated_month(month):
    """Reject a malformed month here rather than deep inside the SQL."""
    if month is None:
        return None
    try:
        aggregations.month_range(month)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"month must look like YYYY-MM, got {month!r}."
        )
    return month


@router.get("/summary", response_model=Summary)
def get_summary(
    month: str | None = Query(None, description="YYYY-MM; omit for all time"),
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
    sheet: str | None = Query(
        None, description="worksheet name; empty string means rows with no sheet"
    ),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Totals, the category split, and the biggest merchants."""
    return aggregations.summary(
        session, validated_month(month), upload_id=upload_id, sheet=sheet,
        user_id=user.id, account_id=account_id,
        entry_source=entry_source,
    )


@router.get("/sources", response_model=list[UploadSource])
def get_sources(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """The files and worksheets that transactions actually came from.

    The source filter is built from this, so its options are whatever is in
    the database — a workbook's tabs appear as tabs, and nothing is listed
    that has no rows behind it.
    """
    return aggregations.sources(session, user_id=user.id)


@router.get("/financial-health", response_model=FinancialHealth)
def get_financial_health(
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
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
    """A 0-100 summary built from the user's own months of history.

    The flagged-spending component reuses the anomaly detector rather than
    approximating it, so the number on this page and the Unusual page describe
    the same rows.
    """
    flagged = find_anomalies(session, sensitivity=sensitivity_for(session, user.id),
        upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)
    flagged_total = sum(float(row["amount"]) for row in flagged)

    return financial_health(
        session, anomaly_total=flagged_total, upload_id=upload_id, sheet=sheet,
        user_id=user.id, account_id=account_id,
        entry_source=entry_source,
    )


@router.get("/trends", response_model=list[TrendPoint])
def get_trends(
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
    sheet: str | None = Query(
        None, description="worksheet name; empty string means rows with no sheet"
    ),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Spend and income per month, oldest first.

    Never narrowed by the month filter — the chart is what you pick a month
    from, so filtering it by that month would leave a single bar.
    """
    return aggregations.monthly_trends(session, upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)
