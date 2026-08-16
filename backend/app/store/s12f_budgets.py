"""Monthly spending limits, and how much of each has been used.

The arithmetic here is deliberately thin. Spending per category already comes
from `aggregations.summary`, which every other page in the app reads, so a
budget is that figure held next to a number the user chose. Computing it a
second way would mean the Budgets page could disagree with the dashboard about
what was spent on food, and both would then be worthless.

Three things this refuses to do:

  - **It does not suggest amounts.** A budget is a decision about how somebody
    wants to live. An app that proposes ₹8,000 for food is guessing at that
    from a spending average, which is a description of the past dressed up as
    advice about the future.
  - **It does not judge.** Over budget is reported as over budget. There is no
    scolding, no "you should", no score.
  - **It does not roll over.** A month is a month. Carrying an underspend
    forward is a different product decision, and doing it silently would make
    the figure on screen unexplainable.
"""

import calendar
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s04_models import Budget
from app.store import s12_aggregations as aggregations
from app.store.s11b_categories import CategoryError, ensure_valid, label_for

ZERO = Decimal("0.00")

# Enough for a real budget; low enough that the page stays readable.
MAX_BUDGETS = 40

# Where a bar turns amber. Not a warning about behaviour — just the point at
# which "how much is left" becomes the more useful reading than "how much has
# gone".
NEAR_LIMIT = 80


class BudgetError(ValueError):
    """A budget that cannot be stored, with a message worth showing."""


def _clean_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except Exception:
        raise BudgetError("Enter the limit as a number, for example 8000.")

    if not amount.is_finite() or amount <= 0:
        raise BudgetError("A budget has to be more than zero.")
    if amount > Decimal("100000000"):
        raise BudgetError("That limit is larger than this app can record.")

    return amount.quantize(Decimal("0.01"))


def _month_key(month=None, today=None) -> str:
    if month:
        try:
            dt.datetime.strptime(month, "%Y-%m")
        except ValueError:
            raise BudgetError("Month must look like YYYY-MM.")
        return month

    today = today or dt.date.today()
    return f"{today.year:04d}-{today.month:02d}"


def list_budgets(session: Session, user_id: int):
    return session.execute(
        select(Budget).where(Budget.user_id == user_id).order_by(Budget.id)
    ).scalars().all()


def set_budget(session: Session, user_id: int, category: str, amount):
    """Create or update the limit for one category.

    Upsert rather than separate create/update endpoints: from the user's side
    there is one question — "what is my limit for food" — and it has one
    answer whether or not they have set it before.
    """
    amount = _clean_amount(amount)

    try:
        ensure_valid(session, user_id, category)
    except CategoryError as error:
        raise BudgetError(str(error))

    existing = session.execute(
        select(Budget).where(
            Budget.user_id == user_id, Budget.category == category
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.amount = amount
        existing.active = True
        existing.updated_at = dt.datetime.now()
        session.commit()
        session.refresh(existing)
        return existing

    if len(list_budgets(session, user_id)) >= MAX_BUDGETS:
        raise BudgetError(f"That is more than {MAX_BUDGETS} budgets.")

    budget = Budget(user_id=user_id, category=category, amount=amount)
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return budget


def update_budget(session: Session, user_id: int, budget_id: int, **changes):
    budget = session.get(Budget, budget_id)
    if budget is None or budget.user_id != user_id:
        return None

    if changes.get("amount") is not None:
        budget.amount = _clean_amount(changes["amount"])
    if changes.get("active") is not None:
        budget.active = bool(changes["active"])

    budget.updated_at = dt.datetime.now()
    session.commit()
    session.refresh(budget)
    return budget


def delete_budget(session: Session, user_id: int, budget_id: int) -> bool:
    """Remove a limit. No transaction is affected — a budget is only a target."""
    budget = session.get(Budget, budget_id)
    if budget is None or budget.user_id != user_id:
        return False

    session.delete(budget)
    session.commit()
    return True


def _days_left(month: str, today: dt.date) -> int:
    """Days remaining in the month, or 0 for a month already finished."""
    year, number = (int(part) for part in month.split("-"))
    if (year, number) != (today.year, today.month):
        return 0

    _, last_day = calendar.monthrange(year, number)
    return last_day - today.day


def budget_progress(session: Session, user_id: int, month=None, today=None):
    """Every budget with what has been spent against it this month.

    Spending comes from the same summary the dashboard uses, so the two can
    never disagree. `available` is false when no budget has been set — which
    is not the same as every budget being at zero, and the page says so.
    """
    today = today or dt.date.today()
    month = _month_key(month, today)

    budgets = [entry for entry in list_budgets(session, user_id) if entry.active]

    if not budgets:
        return {
            "available": False,
            "reason": "No budgets set yet.",
            "month": month,
            "budgets": [],
        }

    summary = aggregations.summary(session, month, user_id=user_id)
    spent_by_category = {
        row["category"]: Decimal(str(row["total"])) for row in summary["by_category"]
    }

    items = []
    for budget in budgets:
        spent = spent_by_category.get(budget.category, ZERO)
        limit = Decimal(str(budget.amount))
        share = int((spent / limit * 100).to_integral_value()) if limit else 0

        items.append({
            "id": budget.id,
            "category": budget.category,
            "label": label_for(session, user_id, budget.category),
            "limit": limit,
            "spent": spent,
            # Never negative: "you have -₹900 left" is arithmetic, not English.
            # The overspend is reported separately, as its own number.
            "remaining": max(ZERO, limit - spent),
            "over_by": max(ZERO, spent - limit),
            "share": share,
            "state": "over" if spent > limit else "near" if share >= NEAR_LIMIT else "ok",
        })

    # Closest to the limit first: those are the ones worth looking at.
    items.sort(key=lambda item: -item["share"])

    total_limit = sum((item["limit"] for item in items), ZERO)
    total_spent = sum((item["spent"] for item in items), ZERO)

    return {
        "available": True,
        "reason": None,
        "month": month,
        "days_left": _days_left(month, today),
        "total_limit": total_limit,
        "total_spent": total_spent,
        "total_remaining": max(ZERO, total_limit - total_spent),
        "over_count": sum(1 for item in items if item["state"] == "over"),
        "budgets": items,
    }
