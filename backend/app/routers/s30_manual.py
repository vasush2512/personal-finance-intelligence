"""Manually entered transactions, and the templates for recording them fast.

There is deliberately no manual transaction *list* endpoint here. A manual row
is an ordinary transaction, so /api/transactions already lists it — with the
same filters, the same pagination and the same search. Adding a second listing
would be a second implementation to keep in step, and the first thing to drift.

What is here is what only applies to rows a person types: creating them,
editing them, removing them, and the small header the Personal Expenses page
opens with.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s01_constants import PAYMENT_METHODS
from app.core.s03_db import get_session
from app.core.s04_models import QuickExpense, User
from app.pipeline.s10h_manual import InvalidEntry, clean_amount
from app.s16a_auth import current_user
from app.s16_schemas import (
    CategorySuggestion,
    ManualEntry,
    ManualEntryUpdate,
    ManualSummary,
    QuickExpenseCreate,
    QuickExpenseOut,
    TransactionOut,
)
from app.store.s11b_categories import CategoryError, ensure_valid, label_for
from app.store.s11c_tags import TagError, set_tags, tags_for
from app.store.s11d_manual import (
    create_manual,
    delete_manual,
    manual_summary,
    suggest_category,
    update_manual,
)

router = APIRouter(prefix="/api", tags=["manual"])


def _out(session: Session, user: User, row) -> TransactionOut:
    """One transaction with its tags attached."""
    result = TransactionOut.model_validate(row)
    result.tags = tags_for(session, user.id, row.id)
    return result


@router.get("/manual/payment-methods", response_model=list[str])
def get_payment_methods(user: User = Depends(current_user)):
    """The payment methods a manual entry may use."""
    return PAYMENT_METHODS


@router.get("/manual/suggest", response_model=CategorySuggestion)
def get_suggestion(
    merchant: str = Query("", max_length=80),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """What the existing rules make of a merchant name, as the user types.

    Returns a null category when nothing matches. The form shows the
    suggestion for acceptance; it never applies it silently, and the user's
    own choice always wins.
    """
    category = suggest_category(session, user.id, merchant)
    return CategorySuggestion(
        category=category,
        label=label_for(session, user.id, category) if category else None,
    )


@router.get("/manual/summary", response_model=ManualSummary)
def get_manual_summary(
    account_id: int | None = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """The Personal Expenses header: today, this month, average, largest."""
    return manual_summary(session, user.id, account_id=account_id)


@router.post("/manual", response_model=TransactionOut, status_code=201)
def post_manual(
    body: ManualEntry,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Record one transaction by hand.

    Fast by design: validate, store, return. No retraining, no re-detection,
    no analytics recomputation — every one of those reads the table when it is
    next asked, so making a person wait for them to record a ₹100 coffee would
    be paying for work nobody asked for yet.
    """
    try:
        row = create_manual(
            session, user.id,
            amount=body.amount, date=body.date, direction=body.direction,
            category=body.category, merchant=body.merchant,
            payment_method=body.payment_method, notes=body.notes,
            account_id=body.account_id,
        )
        if body.tags:
            set_tags(session, user.id, row.id, body.tags)
    except (InvalidEntry, CategoryError, TagError) as error:
        raise HTTPException(status_code=422, detail=str(error))

    return _out(session, user, row)


@router.patch("/manual/{transaction_id}", response_model=TransactionOut)
def patch_manual(
    transaction_id: int,
    body: ManualEntryUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Edit a manual transaction.

    404 for a row that is not this user's AND for an imported row: its amount
    and date came from a bank, and this endpoint will not rewrite those.
    """
    changes = {
        key: value for key, value in body.model_dump().items()
        if value is not None and key != "tags"
    }

    try:
        row = update_manual(session, user.id, transaction_id, **changes)
        if row is not None and body.tags is not None:
            set_tags(session, user.id, transaction_id, body.tags)
    except (InvalidEntry, CategoryError, TagError) as error:
        raise HTTPException(status_code=422, detail=str(error))

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No manual transaction with that id. Imported transactions "
                "cannot be edited here — their amount and date came from your "
                "bank."
            ),
        )

    return _out(session, user, row)


@router.delete("/manual/{transaction_id}", status_code=204)
def remove_manual(
    transaction_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Delete a manual transaction.

    Only manual ones. An imported row belongs to a file, and removing those is
    what deleting the upload does — one at a time would leave the upload's own
    count disagreeing with what is in the database.
    """
    if delete_manual(session, user.id, transaction_id) is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No manual transaction with that id. Imported transactions are "
                "removed by deleting the statement they came from."
            ),
        )
    return None


# --- quick templates -------------------------------------------------------


@router.get("/quick-expenses", response_model=list[QuickExpenseOut])
def get_quick_expenses(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Saved one-click templates. A template is not a transaction."""
    return session.execute(
        select(QuickExpense)
        .where(QuickExpense.user_id == user.id)
        .order_by(QuickExpense.position, QuickExpense.id)
    ).scalars().all()


@router.post("/quick-expenses", response_model=QuickExpenseOut, status_code=201)
def post_quick_expense(
    body: QuickExpenseCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Save a template. Nothing about it appears in any total until used."""
    try:
        amount = clean_amount(body.amount)
        ensure_valid(session, user.id, body.category)
    except (InvalidEntry, CategoryError) as error:
        raise HTTPException(status_code=422, detail=str(error))

    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Give the template a name.")

    template = QuickExpense(
        user_id=user.id,
        name=body.name.strip()[:40],
        emoji=(body.emoji or "")[:8],
        amount=amount,
        direction="credit" if body.direction.lower() in ("income", "credit") else "debit",
        category=body.category,
        merchant_name=(body.merchant_name or "")[:80],
        payment_method=(body.payment_method or "")[:20],
        account_id=body.account_id,
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


@router.post("/quick-expenses/{template_id}/use", response_model=TransactionOut,
             status_code=201)
def use_quick_expense(
    template_id: int,
    on: dt.date | None = Query(None, description="defaults to today"),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Record a transaction from a template, dated today unless told otherwise.

    The template is read, not consumed: it stays saved and can be used again.
    """
    template = session.get(QuickExpense, template_id)
    if template is None or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such quick expense.")

    try:
        row = create_manual(
            session, user.id,
            amount=template.amount,
            date=on or dt.date.today(),
            direction=template.direction,
            category=template.category,
            merchant=template.merchant_name or template.name,
            payment_method=template.payment_method,
            account_id=template.account_id,
        )
    except (InvalidEntry, CategoryError) as error:
        raise HTTPException(status_code=422, detail=str(error))

    return _out(session, user, row)


@router.delete("/quick-expenses/{template_id}", status_code=204)
def remove_quick_expense(
    template_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Delete a template. Transactions already recorded from it are untouched."""
    template = session.get(QuickExpense, template_id)
    if template is None or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such quick expense.")

    session.delete(template)
    session.commit()
    return None
