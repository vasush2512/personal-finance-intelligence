"""Running the plan a question parsed into, and shaping the answer.

Every answer here comes from the same aggregation functions the dashboard uses.
Nothing is computed a second way for the assistant — if the dashboard and an
answer to "how much did I spend last month" ever disagreed, both would become
worthless, and the only way to guarantee they cannot is to have one of them
call the other.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import select

from app.core.s01_constants import UNCATEGORIZED
from app.core.s04_models import Transaction
from app.pipeline.s10g_assistant import parse_question
from app.store import s12_aggregations as aggregations

ZERO = Decimal("0.00")

# How many rows a list-shaped answer returns. Enough to see the shape, few
# enough to read in a chat bubble.
LIST_LIMIT = 5


def _year_conditions(year):
    if not year:
        return []
    return [
        Transaction.date >= dt.date(year, 1, 1),
        Transaction.date < dt.date(year + 1, 1, 1),
    ]


def _months_covered(session, month, year, **source):
    """How many months the answer's period actually contains data for."""
    if month:
        return 1
    trends = aggregations.monthly_trends(session, **source)
    if year:
        trends = [point for point in trends if point["month"].startswith(str(year))]
    return len(trends)


def answer(session, question, today=None, **source):
    """Parse a question, run it, and return the answer with its working."""
    today = today or dt.date.today()
    plan = parse_question(question, today=today)

    if not plan["understood"]:
        return plan

    # No statement, no answer. "Rs 0 across all your data" is technically true
    # and completely misleading — it reads as "you spent nothing", not as
    # "there is nothing here to look at".
    if not _has_any_transactions(session, **source):
        return {
            **plan,
            "answer": None,
            "value": None,
            "rows": [],
            "filters": {},
            "no_data": True,
            "reason": (
                "There is nothing to analyse yet — no statement has been "
                "uploaded. Upload one and ask again."
            ),
        }

    summary = aggregations.summary(session, plan["month"], **source)
    result = {**plan, "answer": None, "value": None, "rows": [], "filters": {}}

    # The filter set the UI turns into a "show me these transactions" link, so
    # every answer can be checked against the actual rows behind it.
    result["filters"] = {
        "month": plan["month"],
        "category": plan["category"],
        "direction": _direction_for(plan["intent"]),
    }

    handler = {
        "total_spend": _total_spend,
        "total_income": _total_income,
        "transaction_count": _transaction_count,
        "top_categories": _top_categories,
        "top_merchants": _top_merchants,
        "largest_transaction": _largest_transaction,
        "average_spend": _average_spend,
    }[plan["intent"]]

    result = handler(session, plan, summary, result, source)

    # Category and merchant names are stored lowercase, and several answers
    # open with one. Capitalising here rather than in each handler keeps the
    # grouping keys untouched — the label is display, the key is data.
    if result.get("answer"):
        result["answer"] = result["answer"][0].upper() + result["answer"][1:]

    return result


def _has_any_transactions(session, **source) -> bool:
    """Whether this user has any rows at all, before answering about them."""
    return session.execute(
        select(Transaction.id)
        .where(*aggregations.source_conditions(**source))
        .limit(1)
    ).first() is not None


def _direction_for(intent):
    if intent == "total_income":
        return "credit"
    if intent in ("total_spend", "largest_transaction", "average_spend"):
        return "debit"
    return None


def _category_total(summary, category):
    for row in summary["by_category"]:
        if row["category"] == category:
            return Decimal(str(row["total"])), row["count"]
    return ZERO, 0


def _total_spend(session, plan, summary, result, source):
    if plan["category"]:
        total, count = _category_total(summary, plan["category"])
        result["value"] = total
        result["answer"] = (
            f"{_money(total)} on {_label(plan['category'])} "
            f"{_period(plan)}, across {count:,} transactions."
        )
        if count == 0:
            result["answer"] = (
                f"Nothing recorded in {_label(plan['category'])} {_period(plan)}."
            )
        return result

    if plan["year"]:
        result["value"] = _sum_debits(session, plan["year"], source)
    else:
        result["value"] = Decimal(str(summary["total_spent"]))

    result["answer"] = f"{_money(result['value'])} {_period(plan)}, transfers excluded."
    return result


def _sum_debits(session, year, source):
    """A year is not a month, so it cannot come from the month-scoped summary."""
    rows = session.execute(
        select(Transaction.amount).where(
            Transaction.direction == "debit",
            Transaction.category != "transfer",
            *_year_conditions(year),
            *aggregations.source_conditions(**source),
        )
    ).scalars().all()
    return sum(rows, ZERO)


def _total_income(session, plan, summary, result, source):
    if plan["year"]:
        rows = session.execute(
            select(Transaction.amount).where(
                Transaction.direction == "credit",
                Transaction.category != "transfer",
                *_year_conditions(plan["year"]),
                *aggregations.source_conditions(**source),
            )
        ).scalars().all()
        result["value"] = sum(rows, ZERO)
    else:
        result["value"] = Decimal(str(summary["total_income"]))

    result["answer"] = f"{_money(result['value'])} came in {_period(plan)}."
    return result


def _transaction_count(session, plan, summary, result, source):
    if plan["category"]:
        _, count = _category_total(summary, plan["category"])
        result["value"] = count
        result["answer"] = (
            f"{count:,} transactions in {_label(plan['category'])} {_period(plan)}."
        )
        return result

    result["value"] = summary["transaction_count"]
    result["answer"] = f"{result['value']:,} transactions {_period(plan)}."
    return result


def _top_categories(session, plan, summary, result, source):
    rows = summary["by_category"][:LIST_LIMIT]
    if not rows:
        result["answer"] = f"No spending recorded {_period(plan)}."
        return result

    total = Decimal(str(summary["total_spent"])) or Decimal("1")
    result["rows"] = [
        {
            "label": _label(row["category"]),
            "value": f"{Decimal(str(row['total'])):.2f}",
            "detail": f"{Decimal(str(row['total'])) / total * 100:.0f}% · {row['count']:,} transactions",
        }
        for row in rows
    ]
    top = rows[0]
    result["value"] = Decimal(str(top["total"]))
    result["answer"] = (
        f"{_label(top['category'])} is your largest, at {_money(top['total'])} "
        f"{_period(plan)}."
    )
    return result


def _top_merchants(session, plan, summary, result, source):
    rows = summary["top_merchants"][:LIST_LIMIT]
    if not rows:
        result["answer"] = f"No merchants recorded {_period(plan)}."
        return result

    result["rows"] = [
        {
            "label": row["merchant"],
            "value": f"{Decimal(str(row['total'])):.2f}",
            "detail": f"{row['count']:,} transactions",
        }
        for row in rows
    ]
    top = rows[0]
    result["value"] = Decimal(str(top["total"]))
    result["answer"] = (
        f"{top['merchant']} — {_money(top['total'])} across "
        f"{top['count']:,} transactions {_period(plan)}."
    )
    return result


def _largest_transaction(session, plan, summary, result, source):
    conditions = [
        Transaction.direction == "debit",
        *aggregations.source_conditions(**source),
    ]
    if plan["category"]:
        conditions.append(Transaction.category == plan["category"])
    if plan["month"]:
        start, end = aggregations.month_range(plan["month"])
        conditions += [Transaction.date >= start, Transaction.date < end]
    conditions += _year_conditions(plan["year"])

    row = session.execute(
        select(Transaction).where(*conditions).order_by(Transaction.amount.desc()).limit(1)
    ).scalars().first()

    if row is None:
        result["answer"] = f"No spending recorded {_period(plan)}."
        return result

    result["value"] = row.amount
    result["rows"] = [
        {
            "label": row.merchant,
            "value": f"{row.amount:.2f}",
            "detail": f"{row.date.isoformat()} · {_label(row.category)}",
        }
    ]
    result["answer"] = (
        f"{_money(row.amount)} at {row.merchant} on {row.date.isoformat()}, "
        f"in {_label(row.category)}."
    )
    return result


def _average_spend(session, plan, summary, result, source):
    months = _months_covered(session, plan["month"], plan["year"], **source)

    if plan["category"]:
        total, _ = _category_total(summary, plan["category"])
    elif plan["year"]:
        total = _sum_debits(session, plan["year"], source)
    else:
        total = Decimal(str(summary["total_spent"]))

    if not months:
        result["answer"] = "There are no months of data to average over yet."
        return result

    average = (total / months).quantize(Decimal("0.01"))
    result["value"] = average
    scope = f" on {_label(plan['category'])}" if plan["category"] else ""
    result["answer"] = (
        f"{_money(average)} a month{scope}, averaged over "
        f"{months} month{'s' if months != 1 else ''} of data."
    )
    return result


def _period(plan):
    if plan["month"]:
        return f"in {plan['month']}"
    if plan["year"]:
        return f"in {plan['year']}"
    return "across all your data"


def _label(category):
    if category == UNCATEGORIZED:
        return "uncategorised"
    if category == "bills_utilities":
        return "bills & utilities"
    return category.replace("_", " ")


def _money(value):
    """Indian grouping, whole rupees, for a sentence."""
    from app.pipeline.s10d_insights import format_money

    return format_money(value)
