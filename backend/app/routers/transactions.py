"""GET /api/transactions — the filtered transaction list."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import CATEGORIES
from app.db import get_session
from app.models import Transaction
from app.schemas import TransactionOut, TransactionPage, TransactionUpdate

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


def build_filters(month, category, search, direction):
    """Translate the query string into a list of SQLAlchemy conditions."""
    conditions = []

    if month:
        start, end = month_bounds(month)
        conditions.append(Transaction.date >= start)
        conditions.append(Transaction.date < end)

    if category:
        if category not in CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown category {category!r}. Valid: {', '.join(CATEGORIES)}",
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


@router.get("/categories", response_model=list[str])
def list_categories():
    """The category vocabulary, for the UI's dropdown.

    Not in PRD 8, but the alternative is copying the list into JavaScript,
    and the house rule is that category names live in constants.py and
    nowhere else. An endpoint keeps that true across languages.
    """
    return list(CATEGORIES)


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    month: str | None = Query(None, description="YYYY-MM"),
    category: str | None = Query(None),
    search: str | None = Query(None, description="substring of the description"),
    direction: str | None = Query(None, description="debit or credit"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """Newest first. `total` counts every match, not just this page."""
    conditions = build_filters(month, category, search, direction)

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

    return TransactionPage(total=total, limit=limit, offset=offset, items=rows)


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def correct_category(
    transaction_id: int,
    update: TransactionUpdate,
    session: Session = Depends(get_session),
):
    """Change one transaction's category.

    Marks the row as 'user'. That label is permanent: neither the rules nor
    the model will overwrite it on a later import or retrain, and it becomes
    training data the next time the model is fitted.
    """
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=404, detail=f"No transaction with id {transaction_id}."
        )

    transaction.category = update.category
    transaction.category_source = "user"
    # A human decided this, so there is no model probability to report.
    transaction.confidence = None

    session.commit()
    session.refresh(transaction)
    return transaction
