"""Monthly spending limits.

A budget is a target the user chose. This endpoint stores it and reports how
much of it has gone — it never proposes an amount, never adjusts one, and
never tells anybody what to do about it.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import BudgetOut, BudgetProgress, BudgetSet, BudgetUpdate
from app.store.s12f_budgets import (
    BudgetError,
    budget_progress,
    delete_budget,
    list_budgets,
    set_budget,
    update_budget,
)

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
def get_budgets(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Every limit this user has set."""
    return list_budgets(session, user.id)


@router.get("/progress", response_model=BudgetProgress)
def get_progress(
    month: str | None = Query(None, description="YYYY-MM; defaults to this month"),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Each budget against what has been spent on it.

    Spending is read from the same summary the dashboard uses, so the two
    cannot disagree about what went on food this month.
    """
    try:
        return budget_progress(session, user.id, month=month)
    except BudgetError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("", response_model=BudgetOut, status_code=201)
def post_budget(
    body: BudgetSet,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Set the limit for a category, creating or replacing it.

    Deliberately an upsert. From the user's side there is one question — what
    is my limit for food — and it has one answer whether or not they have
    answered it before.
    """
    try:
        return set_budget(session, user.id, body.category, body.amount)
    except BudgetError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.patch("/{budget_id}", response_model=BudgetOut)
def patch_budget(
    budget_id: int,
    body: BudgetUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Change the amount, or pause it for a while."""
    try:
        budget = update_budget(session, user.id, budget_id, **body.model_dump())
    except BudgetError as error:
        raise HTTPException(status_code=422, detail=str(error))

    if budget is None:
        raise HTTPException(status_code=404, detail="No such budget.")
    return budget


@router.delete("/{budget_id}", status_code=204)
def remove_budget(
    budget_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Remove a limit. No transaction is affected — it was only a target."""
    if not delete_budget(session, user.id, budget_id):
        raise HTTPException(status_code=404, detail="No such budget.")
    return None
