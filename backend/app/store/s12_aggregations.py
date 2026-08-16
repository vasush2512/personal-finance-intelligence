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

# Categories that are movements, not spending.
NON_SPENDING = ("transfer",)

# Categories that are not earnings. A refund is money returning, not money
# made — counting it as income overstates what you actually took in, and every
# figure derived from income (savings rate, health, the forecast) inherits
# that error. See REFUND in constants.py for why it is not netted off
# spending instead.
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
    """Filter conditions for one month, or none at all when month is None."""
    if not month:
        return []
    start, end = month_range(month)
    return [Transaction.date >= start, Transaction.date < end]


def source_conditions(upload_id=None, sheet=None, user_id=None, account_id=None,
                      entry_source=None):
    """Restrict to one user, and optionally to one file or worksheet.

    `user_id` rides along with the source filter rather than being a separate
    argument threaded through twenty functions, because every one of them
    already accepts and forwards `**source`. Adding it here means ownership
    reaches every aggregation, trend, anomaly and detector at once — including
    any written later, which is the part that matters.

    `entry_source` narrows to statements or to manual entries. Both are the
    same kind of row and are aggregated together by default; this exists so
    the user can ask "what did I type in myself?" without the app keeping two
    sets of books to answer it.

    `account_id` narrows to one bank account, which is the filter people reach
    for most once more than one statement is loaded.

    `sheet=""` is not the same as `sheet=None`: the empty string means "rows
    that came from a single-table file", which is every CSV and JSON row,
    while None means no restriction at all.
    """
    conditions = []

    if user_id is not None:
        conditions.append(Transaction.user_id == user_id)

    if entry_source is not None:
        if entry_source == ENTRY_STATEMENT:
            # NULL means statement: every row imported before manual entry
            # existed came from one, and its absence already says so. Matching
            # only the literal string here would hide a hundred thousand rows.
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
    """SUM over a filtered set, as Decimal. Empty set means 0.00, not None."""
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
    """Spending per category, biggest first."""
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


def top_merchants(session: Session, month=None, limit=TOP_MERCHANT_LIMIT, **source):
    """Biggest merchants by total spend."""
    merchant = _merchant_expression()

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
    """How many rows each labeller is responsible for.

    'rule' / 'model' / 'user' is the story of how the categorization is
    doing: rules cover the obvious merchants, the model reaches the ones no
    rule names, and a growing 'user' count is the training data that makes
    the accuracy figure mean something.
    """
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
            .where(*source_conditions(user_id=user_id))
            .group_by(Transaction.category)
        ).all()
    )

    return [
        {"category": category, "count": counted.get(category, 0)}
        for category in CATEGORIES
    ]


def sources(session: Session, user_id=None):
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
        # Scoped on the transactions rather than on Upload.user_id: the rows
        # are what the filter actually selects, and an upload with none of the
        # caller's rows in it is not a source they can filter to.
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
    """Everything the summary cards and the category chart need.

    The source filter reaches every number here, not just the table below
    them. A dashboard where the filter moves the list but leaves the totals
    describing the whole database is worse than one with no filter at all.
    """
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
    """Spend and income per month, oldest first.

    Months with no transactions are not invented - the chart shows the
    months the statements actually cover, and under a source filter that
    means the months that file covers.
    """
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
