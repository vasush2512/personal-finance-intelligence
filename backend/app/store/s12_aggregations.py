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

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.s01_constants import (
    CATEGORIES,
    CATEGORY_SOURCES,
    ENTRY_STATEMENT,
    REFUND,
)
from app.core.s04_models import Transaction, Upload

NON_SPENDING = ("transfer",)
NON_INCOME = ("transfer", REFUND)
TOP_MERCHANT_LIMIT = 10
ZERO = Decimal("0.00")


def month_range(month: str):
    """'2026-05' -> (date(2026,5,1), date(2026,6,1)). Half-open."""
    start = dt.datetime.strptime(month, "%Y-%m").date()
    if start.month == 12:
        return start, dt.date(start.year + 1, 1, 1)
    return start, dt.date(start.year, start.month + 1, 1)


def month_conditions(month):
    if not month:
        return []
    start, end = month_range(month)
    return [Transaction.date >= start, Transaction.date < end]


def source_conditions(upload_id=None, sheet=None, user_id=None, account_id=None,
                      entry_source=None):
    conditions = []
    if user_id is not None:
        conditions.append(Transaction.user_id == user_id)

    if entry_source is not None:
        if entry_source == ENTRY_STATEMENT:
            conditions.append(
                or_(
                    Transaction.entry_source.is_(None),
                    Transaction.entry_source == ENTRY_STATEMENT,
                )
            )
        else:
            conditions.append(Transaction.entry_source == entry_source)

    if account_id is not None:
        conditions.append(Transaction.account_id == account_id)
    if upload_id is not None:
        conditions.append(Transaction.upload_id == upload_id)

    if sheet is not None:
        if sheet == "":
            conditions.append(Transaction.sheet_name.is_(None))
        else:
            conditions.append(Transaction.sheet_name == sheet)
    return conditions


def spending_conditions():
    return [
        Transaction.direction == "debit",
        Transaction.category.notin_(NON_SPENDING),
    ]


def income_conditions():
    return [
        Transaction.direction == "credit",
        Transaction.category.notin_(NON_INCOME),
    ]


def _total(session: Session, conditions):
    total = session.execute(
        select(func.sum(Transaction.amount)).where(*conditions)
    ).scalar()
    return total if total is not None else ZERO


def total_spent(session: Session, month=None, **source) -> Decimal:
    return _total(
        session,
        spending_conditions() + month_conditions(month) + source_conditions(**source),
    )


def total_income(session: Session, month=None, **source) -> Decimal:
    return _total(
        session,
        income_conditions() + month_conditions(month) + source_conditions(**source),
    )


def transaction_count(session: Session, month=None, **source) -> int:
    return session.execute(
        select(func.count(Transaction.id)).where(
            *(month_conditions(month) + source_conditions(**source))
        )
    ).scalar_one()


def totals_by_category(session: Session, month=None, **source):
    rows = session.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .where(*(spending_conditions() + month_conditions(month) + source_conditions(**source)))
        .group_by(Transaction.category)
    ).all()

    results = [
        {"category": category, "total": total, "count": count}
        for category, total, count in rows
    ]
    results.sort(key=lambda row: row["total"], reverse=True)
    return results


def merchant_name(normalized_description: str) -> str:
    words = (normalized_description or "").split()
    return words[0] if words else "unknown"


def _merchant_expression(session: Session):
    """Build the first-word merchant expression for the active database."""
    description = Transaction.normalized_description
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        space_at = func.strpos(description, " ")
    else:
        space_at = func.instr(description, " ")

    return case(
        (description == "", "unknown"),
        (space_at > 0, func.substr(description, 1, space_at - 1)),
        else_=description,
    )


def top_merchants(session: Session, month=None, limit=TOP_MERCHANT_LIMIT, **source):
    merchant = _merchant_expression(session)

    rows = session.execute(
        select(merchant, func.sum(Transaction.amount), func.count(Transaction.id))
        .where(*(spending_conditions() + month_conditions(month) + source_conditions(**source)))
        .group_by(merchant)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    ).all()

    return [
        {"merchant": name or "unknown", "total": total, "count": count}
        for name, total, count in rows
    ]


def counts_by_category_source(session: Session, month=None, **source):
    rows = session.execute(
        select(Transaction.category_source, func.count(Transaction.id))
        .where(*(month_conditions(month) + source_conditions(**source)))
        .group_by(Transaction.category_source)
    ).all()

    counted = dict(rows)
    return [
        {"source": label, "count": counted.get(label, 0)}
        for label in CATEGORY_SOURCES
    ]


def category_counts(session: Session, user_id=None):
    counted = dict(
        session.execute(
            select(Transaction.category, func.count(Transaction.id))
            .where(*source_conditions(user_id=user_id))
            .group_by(Transaction.category)
        ).all()
    )

    return [
        {"category": category, "count": counted.get(category, 0)}
        for category in CATEGORIES
    ]


def sources(session: Session, user_id=None):
    rows = session.execute(
        select(
            Upload.id,
            Upload.filename,
            Upload.uploaded_at,
            Transaction.sheet_name,
            func.count(Transaction.id),
        )
        .join(Transaction, Transaction.upload_id == Upload.id)
        .where(*source_conditions(user_id=user_id))
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


def summary(session: Session, month=None, **source) -> dict:
    spent = total_spent(session, month, **source)
    income = total_income(session, month, **source)

    return {
        "total_spent": spent,
        "total_income": income,
        "net": income - spent,
        "transaction_count": transaction_count(session, month, **source),
        "by_category": totals_by_category(session, month, **source),
        "by_category_source": counts_by_category_source(session, month, **source),
        "top_merchants": top_merchants(session, month, **source),
    }


def monthly_trends(session: Session, **source):
    """Spend and income per month, using the active database's date function."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        month_column = func.to_char(Transaction.date, "YYYY-MM")
    else:
        month_column = func.strftime("%Y-%m", Transaction.date)

    rows = session.execute(
        select(month_column, Transaction.direction, func.sum(Transaction.amount))
        .where(
            Transaction.category.notin_(NON_SPENDING), *source_conditions(**source)
        )
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
