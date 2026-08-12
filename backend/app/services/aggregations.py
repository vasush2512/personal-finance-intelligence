"""Dashboard arithmetic: totals, per-category splits, monthly trends.

All of it lives here rather than in the route handlers, and all of it works
in Decimal. Money never becomes a float on the way to the dashboard.

What counts as spending
-----------------------
Debits only, and 'transfer' is excluded. Moving money to your own account or
withdrawing cash is not an expense - counting it would inflate every total
and make the category chart lie. Income is a credit and so is never in a
spending total to begin with.
"""

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Transaction

# Categories that are movements, not spending.
NON_SPENDING = ("transfer",)

TOP_MERCHANT_LIMIT = 10
ZERO = Decimal("0.00")


def month_range(month: str):
    """'2026-05' -> (date(2026,5,1), date(2026,6,1)). Half-open."""
    start = dt.datetime.strptime(month, "%Y-%m").date()
    if start.month == 12:
        return start, dt.date(start.year + 1, 1, 1)
    return start, dt.date(start.year, start.month + 1, 1)


def month_conditions(month):
    """Filter conditions for one month, or none at all when month is None."""
    if not month:
        return []
    start, end = month_range(month)
    return [Transaction.date >= start, Transaction.date < end]


def spending_conditions():
    return [
        Transaction.direction == "debit",
        Transaction.category.notin_(NON_SPENDING),
    ]


def income_conditions():
    return [
        Transaction.direction == "credit",
        Transaction.category.notin_(NON_SPENDING),
    ]


def _total(session: Session, conditions):
    """SUM over a filtered set, as Decimal. Empty set means 0.00, not None."""
    total = session.execute(
        select(func.sum(Transaction.amount)).where(*conditions)
    ).scalar()
    return total if total is not None else ZERO


def total_spent(session: Session, month=None) -> Decimal:
    return _total(session, spending_conditions() + month_conditions(month))


def total_income(session: Session, month=None) -> Decimal:
    return _total(session, income_conditions() + month_conditions(month))


def transaction_count(session: Session, month=None) -> int:
    return session.execute(
        select(func.count(Transaction.id)).where(*month_conditions(month))
    ).scalar_one()


def totals_by_category(session: Session, month=None):
    """Spending per category, biggest first."""
    rows = session.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .where(*(spending_conditions() + month_conditions(month)))
        .group_by(Transaction.category)
    ).all()

    results = [
        {"category": category, "total": total, "count": count}
        for category, total, count in rows
    ]
    results.sort(key=lambda row: row["total"], reverse=True)
    return results


def merchant_name(normalized_description: str) -> str:
    """First word of the normalized narration, used as the merchant.

    'blinkit groceries' -> 'blinkit'. Crude but effective on real narrations,
    where the merchant almost always leads. It does mislabel a few rows
    ('house rent march' -> 'house'), which is why this is a display-only
    grouping and never a stored field.
    """
    words = (normalized_description or "").split()
    return words[0] if words else "unknown"


def top_merchants(session: Session, month=None, limit=TOP_MERCHANT_LIMIT):
    """Biggest merchants by total spend.

    Grouped in Python because the merchant is derived from the text, and
    SQLite has no clean way to split a string inside a GROUP BY.
    """
    rows = session.execute(
        select(Transaction.normalized_description, Transaction.amount)
        .where(*(spending_conditions() + month_conditions(month)))
    ).all()

    totals = defaultdict(lambda: {"total": ZERO, "count": 0})
    for description, amount in rows:
        entry = totals[merchant_name(description)]
        entry["total"] += amount
        entry["count"] += 1

    merchants = [
        {"merchant": name, "total": entry["total"], "count": entry["count"]}
        for name, entry in totals.items()
    ]
    merchants.sort(key=lambda row: row["total"], reverse=True)
    return merchants[:limit]


def summary(session: Session, month=None) -> dict:
    """Everything the summary cards and the category chart need."""
    spent = total_spent(session, month)
    income = total_income(session, month)

    return {
        "total_spent": spent,
        "total_income": income,
        "net": income - spent,
        "transaction_count": transaction_count(session, month),
        "by_category": totals_by_category(session, month),
        "top_merchants": top_merchants(session, month),
    }


def monthly_trends(session: Session):
    """Spend and income per month, oldest first.

    Months with no transactions are not invented - the chart shows the
    months the statements actually cover.
    """
    rows = session.execute(
        select(
            func.strftime("%Y-%m", Transaction.date),
            Transaction.direction,
            Transaction.category,
            Transaction.amount,
        )
    ).all()

    by_month = defaultdict(lambda: {"spent": ZERO, "income": ZERO})
    for month, direction, category, amount in rows:
        if category in NON_SPENDING:
            continue
        if direction == "debit":
            by_month[month]["spent"] += amount
        else:
            by_month[month]["income"] += amount

    return [
        {"month": month, "spent": values["spent"], "income": values["income"]}
        for month, values in sorted(by_month.items())
    ]
