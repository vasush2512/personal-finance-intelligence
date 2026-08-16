"""One month, written out in sentences (PRD Part 26).

The dashboard shows a month as numbers in boxes. This says the same thing as
prose, because a sentence carries the relationship between two figures in a way
four separate cards do not: "you spent more than came in" lands differently
from a red minus sign.

The sentences are templates filled from figures that were already computed.
Nothing is generated in the language-model sense, nothing is estimated, and
there is no advice — "you spent 32% more on food" belongs here; "you should
cook at home" does not, and the PRD rules it out.

A paragraph is omitted rather than hedged when its figures are not there. A
story that says "your spending changed by 0%" for a first month is worse than
a story with one paragraph fewer.
"""

from app.pipeline.s10d_insights import format_category, format_money

# Below this, a month-on-month move is noise and gets no sentence.
MIN_CHANGE_PERCENT = 5

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def month_title(month):
    """'2026-07' -> 'July 2026'."""
    try:
        year, number = month.split("-")
        return f"{_MONTH_NAMES[int(number) - 1]} {year}"
    except (ValueError, IndexError, AttributeError):
        return month


def _opening(summary):
    """What came in, what went out, what was left."""
    spent = float(summary.get("total_spent") or 0)
    income = float(summary.get("total_income") or 0)
    count = summary.get("transaction_count") or 0

    if not spent and not income:
        return None

    sentence = (
        f"{format_money(income)} came in and {format_money(spent)} went out "
        f"across {count:,} transactions."
    )

    if income > 0:
        net = income - spent
        if net >= 0:
            share = net / income * 100
            sentence += (
                f" That left {format_money(net)}, or {share:.0f}% of what you "
                f"earned."
            )
        else:
            sentence += (
                f" That is {format_money(abs(net))} more than came in, so the "
                f"difference came out of what you already had."
            )

    return sentence


def _where_it_went(summary):
    """The categories that made up the month."""
    spent = float(summary.get("total_spent") or 0)
    categories = summary.get("by_category") or []

    if not categories or spent <= 0:
        return None

    top = categories[:3]
    parts = [
        f"{format_category(row['category'])} ({format_money(row['total'])})"
        for row in top
    ]
    share = sum(float(row["total"]) for row in top) / spent * 100

    if len(parts) == 1:
        listed = parts[0]
    else:
        listed = f"{', '.join(parts[:-1])} and {parts[-1]}"

    return (
        f"Most of it went to {listed} — together {share:.0f}% of everything "
        f"you spent."
    )


def _versus_last_month(summary, previous, month):
    """How this month compared with the one before it."""
    if not previous:
        return None

    spent = float(summary.get("total_spent") or 0)
    before = float(previous.get("spent") or 0)
    if not before:
        return None

    change = (spent - before) / before * 100
    if abs(change) < MIN_CHANGE_PERCENT:
        return (
            f"That is about the same as {month_title(previous['month'])}, "
            f"within {MIN_CHANGE_PERCENT}%."
        )

    direction = "more" if change > 0 else "less"
    return (
        f"You spent {abs(change):.0f}% {direction} than in "
        f"{month_title(previous['month'])}, when the total was "
        f"{format_money(before)}."
    )


def _worth_a_look(anomalies):
    """Transactions the statistics flagged, worded as a prompt to check."""
    if not anomalies:
        return None

    total = sum(float(row["amount"]) for row in anomalies)
    count = len(anomalies)
    largest = max(anomalies, key=lambda row: float(row["amount"]))

    sentence = (
        f"{count} transaction{'s' if count != 1 else ''} stood out against the "
        f"usual for their category, {format_money(total)} in total"
    )
    if count > 1:
        sentence += f", the largest being {format_money(largest['amount'])}"
    sentence += (
        ". Standing out is a statistical comparison, not a sign anything is "
        "wrong — it is a prompt to check, nothing more."
    )
    return sentence


def _commitments(recurring):
    """What of the month was already spoken for."""
    if not recurring:
        return None

    count = len(recurring)
    total = sum(float(row["average_amount"]) for row in recurring)

    return (
        f"{count} recurring payment{'s' if count != 1 else ''} account for "
        f"about {format_money(total)} of a typical month — the part of your "
        f"spending that is committed before the month begins."
    )


def build_story(month, summary, previous=None, anomalies=None, recurring=None):
    """A month as paragraphs, with the figures behind each one.

    `previous` is the trend point for the month before, or None for the first
    month in the data. `available` is False when the month has no transactions
    at all, so the UI can say so rather than print an empty page.
    """
    paragraphs = [
        paragraph
        for paragraph in (
            _opening(summary),
            _where_it_went(summary),
            _versus_last_month(summary, previous, month),
            _worth_a_look(anomalies),
            _commitments(recurring),
        )
        if paragraph
    ]

    if not paragraphs:
        return {
            "available": False,
            "month": month,
            "title": month_title(month),
            "reason": f"There are no transactions recorded for {month_title(month)}.",
            "paragraphs": [],
        }

    return {
        "available": True,
        "month": month,
        "title": month_title(month),
        "reason": None,
        "paragraphs": paragraphs,
    }
