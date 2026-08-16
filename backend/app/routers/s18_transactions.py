"""GET /api/transactions — the filtered transaction list."""

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.s01_constants import CATEGORIES, SOURCE_USER
from app.core.s03_db import get_session
from app.s16a_auth import current_user
from app.core.s04_models import Transaction, User
from app.s16_schemas import (
    CategoryOption,
    TransactionDetail,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.store.s14a_detail import transaction_detail
from app.store.s11b_categories import valid_categories
from app.store.s11c_tags import tags_for_many, transaction_ids_with_tag
from app.store.s14c_feedback import record_correction
from app.store import s12_aggregations as aggregations

router = APIRouter(prefix="/api", tags=["transactions"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def month_bounds(month: str):
    """'2026-05' -> (date(2026,5,1), date(2026,6,1)).

    Returns a half-open range so the query is a plain >= / < comparison and
    never has to know how many days the month has.
    """
    try:
        start = dt.datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"month must look like YYYY-MM, got {month!r}.",
        )

    if start.month == 12:
        end = dt.date(start.year + 1, 1, 1)
    else:
        end = dt.date(start.year, start.month + 1, 1)
    return start, end


def build_filters(month, category, search, direction, upload_id=None, sheet=None,
                  user_id=None, account_id=None, entry_source=None,
                  transaction_ids=None, date_from=None, date_to=None,
                  min_amount=None, max_amount=None, payment_method=None,
                  session=None):
    """Translate the query string into a list of SQLAlchemy conditions.

    `user_id` is not optional in practice — every caller is a route that has
    already resolved a signed-in user. It is keyword-with-default only so the
    signature stays readable, and every call site passes it.
    """
    # Same source rules the charts use, so the table can never disagree
    # with the totals above it.
    conditions = aggregations.source_conditions(
        upload_id=upload_id, sheet=sheet, user_id=user_id, account_id=account_id,
        entry_source=entry_source,
    )

    # The tag filter arrives as a set of ids the caller already resolved, so
    # this stays one query rather than a join that every unfiltered request
    # would also pay for.
    if transaction_ids is not None:
        conditions.append(Transaction.id.in_(transaction_ids or [-1]))

    if month:
        start, end = month_bounds(month)
        conditions.append(Transaction.date >= start)
        conditions.append(Transaction.date < end)

    # An explicit range, which is what every date preset resolves to. Inclusive
    # at both ends: "1 Jan to 31 Jan" should contain the 31st, which is what a
    # person means by it.
    if date_from:
        conditions.append(Transaction.date >= date_from)
    if date_to:
        conditions.append(Transaction.date <= date_to)

    if min_amount is not None:
        conditions.append(Transaction.amount >= min_amount)
    if max_amount is not None:
        conditions.append(Transaction.amount <= max_amount)

    if payment_method:
        conditions.append(Transaction.payment_method == payment_method)

    if category:
        # Validated against the built-in list AND this user's own categories.
        # Checking only the built-in twelve would 422 anyone who filtered by a
        # category they created themselves.
        allowed = (
            valid_categories(session, user_id)
            if session is not None and user_id is not None
            else set(CATEGORIES)
        )
        if category not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown category {category!r}.",
            )
        conditions.append(Transaction.category == category)

    if direction:
        if direction not in ("debit", "credit"):
            raise HTTPException(
                status_code=422,
                detail="direction must be 'debit' or 'credit'.",
            )
        conditions.append(Transaction.direction == direction)

    if search:
        conditions.append(Transaction.description.ilike(f"%{search}%"))

    return conditions


@router.get("/categories", response_model=list[CategoryOption])
def list_categories(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """The category vocabulary with row counts.

    Not in PRD 8, but the alternative is copying the list into JavaScript,
    and the house rule is that category names live in constants.py and
    nowhere else. An endpoint keeps that true across languages.

    All twelve come back, empty ones included. The filter shows only those
    with rows; the table's dropdown needs the whole list so a transaction can
    be moved into a category nothing uses yet.
    """
    return aggregations.category_counts(session, user_id=user.id)


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    month: str | None = Query(None, description="YYYY-MM"),
    category: str | None = Query(None),
    search: str | None = Query(None, description="substring of the description"),
    direction: str | None = Query(None, description="debit or credit"),
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
    tag: str | None = Query(None, description="only rows carrying this tag"),
    date_from: dt.date | None = Query(None, description="inclusive start date"),
    date_to: dt.date | None = Query(None, description="inclusive end date"),
    min_amount: Decimal | None = Query(None, ge=0),
    max_amount: Decimal | None = Query(None, ge=0),
    payment_method: str | None = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Newest first. `total` counts every match, not just this page.

    Manual and imported rows are listed together by default — they are the
    same kind of thing. `entry_source` narrows to one; `tag` narrows to a
    label the user attached.
    """
    conditions = build_filters(
        month, category, search, direction, upload_id, sheet,
        user_id=user.id, account_id=account_id, entry_source=entry_source,
        # Resolved to ids here rather than joined in build_filters, so an
        # unfiltered request does not pay for a join it never uses.
        transaction_ids=(
            transaction_ids_with_tag(session, user.id, tag) if tag else None
        ),
        date_from=date_from, date_to=date_to,
        min_amount=min_amount, max_amount=max_amount,
        payment_method=payment_method,
        session=session,
    )

    total = session.execute(
        select(func.count(Transaction.id)).where(*conditions)
    ).scalar_one()

    rows = session.execute(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    # Tags for the whole page in one query rather than one per row.
    items = [TransactionOut.model_validate(row) for row in rows]
    grouped = tags_for_many(session, user.id, [row.id for row in rows])
    for item in items:
        item.tags = grouped.get(item.id, [])

    return TransactionPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/transactions/{transaction_id}", response_model=TransactionDetail)
def get_transaction(
    transaction_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """One transaction, with the analysis behind any flag on it.

    Separate from the list endpoint on purpose: assembling this runs a peer
    query over the category's trailing six months, which would be wasted on
    fifty rows the user has not opened.
    """
    detail = transaction_detail(session, transaction_id, user_id=user.id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"No transaction with id {transaction_id}."
        )
    return detail


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def correct_category(
    transaction_id: int,
    update: TransactionUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Change one transaction's category.

    Marks the row as 'user'. That label is permanent: neither the rules nor
    the model will overwrite it on a later import or retrain, and it becomes
    training data the next time the model is fitted.

    The change is also written to category_feedback, which is what lets the
    Model page say how often each labeller has been overruled.
    """
    transaction = session.get(Transaction, transaction_id)
    # Someone else's row is reported as missing rather than forbidden:
    # confirming it exists would tell an attacker which ids are real.
    if transaction is None or transaction.user_id != user.id:
        raise HTTPException(
            status_code=404, detail=f"No transaction with id {transaction_id}."
        )

    # Before the assignment below, while the row still knows what it was.
    record_correction(session, transaction, update.category)

    transaction.category = update.category
    transaction.category_source = SOURCE_USER
    # A human decided this, so there is no model probability to report.
    transaction.confidence = None

    session.commit()
    session.refresh(transaction)
    return transaction
