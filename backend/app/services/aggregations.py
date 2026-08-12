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

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.constants import CATEGORIES
from app.models import Transaction, Upload

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


def _merchant_expression():
    """The same first-word rule as merchant_name(), expressed in SQL.

    Doing it here rather than in Python is what keeps this query from
    dragging every spending row into memory just to read its first word.
    A space at position n means the merchant is the first n-1 characters;
    no space means the whole string is the merchant.
    """
    description = Transaction.normalized_description
    space_at = func.instr(description, " ")
    return case(
        (description == "", "unknown"),
        (space_at > 0, func.substr(description, 1, space_at - 1)),
        else_=description,
    )


def top_merchants(session: Session, month=None, limit=TOP_MERCHANT_LIMIT):
    """Biggest merchants by total spend."""
    merchant = _merchant_expression()

    rows = session.execute(
        select(merchant, func.sum(Transaction.amount), func.count(Transaction.id))
        .where(*(spending_conditions() + month_conditions(month)))
        .group_by(merchant)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    ).all()

    return [
        {"merchant": name or "unknown", "total": total, "count": count}
        for name, total, count in rows
    ]


def category_counts(session: Session):
    """Every category in the vocabulary, with how many rows carry it.

    All twelve are returned, including the empty ones, because two callers
    need different halves: the filter shows only categories that have rows,
    while the table's dropdown has to offer every category — you cannot move
    a transaction into a category that no row uses yet if it is not listed.

    Unlike the spending breakdown this counts transfers and income too. They
    are excluded from totals, not from existence.
    """
    counted = dict(
        session.execute(
            select(Transaction.category, func.count(Transaction.id))
            .group_by(Transaction.category)
        ).all()
    )

    return [
        {"category": category, "count": counted.get(category, 0)}
        for category in CATEGORIES
    ]


def sources(session: Session):
    """Every upload that still has rows, with its sheets and their counts.

    Uploads that imported nothing are left out: a re-upload of a statement
    you already had is a real event, but it is not a place transactions can
    be filtered to, and listing it would give the filter dead options.
    """
    rows = session.execute(
        select(
            Upload.id,
            Upload.filename,
            Upload.uploaded_at,
            Transaction.sheet_name,
            func.count(Transaction.id),
        )
        .join(Transaction, Transaction.upload_id == Upload.id)
        .group_by(Upload.id, Transaction.sheet_name)
        .order_by(Upload.uploaded_at.desc(), Transaction.sheet_name)
    ).all()

    uploads = {}
    for upload_id, filename, uploaded_at, sheet_name, count in rows:
        entry = uploads.setdefault(
            upload_id,
            {
                "upload_id": upload_id,
                "filename": filename,
                "uploaded_at": uploaded_at,
                "count": 0,
                "sheets": [],
            },
        )
        entry["count"] += count
        entry["sheets"].append({"sheet_name": sheet_name, "count": count})

    return list(uploads.values())


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
    month_column = func.strftime("%Y-%m", Transaction.date)

    rows = session.execute(
        select(month_column, Transaction.direction, func.sum(Transaction.amount))
        .where(Transaction.category.notin_(NON_SPENDING))
        .group_by(month_column, Transaction.direction)
    ).all()

    by_month = defaultdict(lambda: {"spent": ZERO, "income": ZERO})
    for month, direction, total in rows:
        key = "spent" if direction == "debit" else "income"
        by_month[month][key] += total

    return [
        {"month": month, "spent": values["spent"], "income": values["income"]}
        for month, values in sorted(by_month.items())
    ]
