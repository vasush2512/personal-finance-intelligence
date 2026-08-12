"""Flag unusual spending (PRD 7.4).

Deliberately plain statistics rather than IsolationForest. Two reasons:
the user needs a reason they can read ("3.2x your usual"), and you need to be
able to explain the method in an interview without hand-waving.

Rule: within a category, over the trailing 6 months, flag a debit whose
amount exceeds mean + 2.5 * standard deviation. Requires at least 8 prior
transactions in that category, otherwise the mean is meaningless.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, pstdev

MIN_HISTORY = 8
SIGMA = 2.5
LOOKBACK_DAYS = 183


def _format_inr(amount):
    """1234567.5 -> '12,34,567.50' (Indian digit grouping)."""
    quantized = f"{Decimal(str(amount)):.2f}"
    whole, _, fraction = quantized.partition(".")
    negative = whole.startswith("-")
    whole = whole.lstrip("-")

    if len(whole) > 3:
        last_three = whole[-3:]
        rest = whole[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        whole = ",".join(groups + [last_three])

    return ("-" if negative else "") + whole + "." + fraction


def detect_anomalies(transactions, today=None):
    """Return a list of flagged transactions with a reason string.

    Expects dicts with: date (ISO), amount (str), direction, category.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=LOOKBACK_DAYS)

    recent = []
    for txn in transactions:
        if txn.get("direction") != "debit":
            continue
        txn_date = date.fromisoformat(txn["date"])
        if txn_date >= cutoff:
            recent.append((txn_date, txn))

    by_category = defaultdict(list)
    for _, txn in recent:
        by_category[txn.get("category")].append(float(txn["amount"]))

    flagged = []
    for txn_date, txn in recent:
        category = txn.get("category")
        amounts = by_category[category]
        if len(amounts) < MIN_HISTORY + 1:
            continue

        others = list(amounts)
        others.remove(float(txn["amount"]))   # don't let the outlier skew its own baseline
        if len(others) < MIN_HISTORY:
            continue

        baseline = mean(others)
        spread = pstdev(others)
        amount = float(txn["amount"])

        # Degenerate case: every past transaction in this category is the same
        # amount (a fixed subscription, say), so the standard deviation is 0
        # and mean + 2.5*sigma can never be exceeded. Fall back to a ratio
        # test so a genuinely large charge still gets flagged.
        threshold = baseline + SIGMA * spread if spread > 0 else baseline * 1.5

        if amount <= threshold:
            continue

        ratio = amount / baseline if baseline else 0
        flagged.append(
            {
                **txn,
                "is_anomaly": True,
                "reason": (
                    f"Rs {_format_inr(amount)} on {category} — "
                    f"{ratio:.1f}x your usual Rs {_format_inr(baseline)}"
                ),
            }
        )

    flagged.sort(key=lambda t: t["date"], reverse=True)
    return flagged
