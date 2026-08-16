"""Cash flow projection from a run of complete months (PRD Part 20).

This is arithmetic on months that already happened. It is not a prediction of
the future, and nothing here should ever be worded as one — the honest claim is
"your last five Augusts-to-Decembers came to roughly this, so a similar month
would too", and the range is shown next to the figure so the width of the
uncertainty is visible rather than implied.

Three decisions that keep it honest:

  - **Partial months are excluded.** The month in progress is the single most
    dangerous input a forecast can take: on the 3rd of the month it is 90%
    missing, and averaging it in drags every projection down. Only months that
    have completely finished are used.
  - **The median, not the mean.** One holiday month should not move the
    baseline for the next six.
  - **The range is the real spread**, not a percentage band invented to look
    like statistics. Low and high are the actual smallest and largest of the
    months used, so "between X and Y" is a sentence about real months.

Below MIN_MONTHS it returns available=False with a reason, rather than a number
built on too little to mean anything.
"""

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

# Two months give one comparison, which is not a baseline. Three is the fewest
# that can show a level rather than a change.
MIN_MONTHS = 3

# How far back the baseline reaches. Longer than this and old habits outweigh
# recent ones; shorter and one unusual month dominates.
LOOKBACK_MONTHS = 6

ZERO = Decimal("0.00")


def _money(value):
    """Whatever the caller passed -> Decimal, rounded to paise."""
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _median(values):
    """Middle value; the average of the middle two when the count is even."""
    ordered = sorted(values)
    count = len(ordered)
    if not count:
        return ZERO
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return _money((ordered[middle - 1] + ordered[middle]) / 2)


def _next_month(month):
    """'2026-07' -> '2026-08'."""
    year, number = (int(part) for part in month.split("-"))
    return f"{year + 1:04d}-01" if number == 12 else f"{year:04d}-{number + 1:02d}"


def _spread(values, middle):
    """How far the months sit from their own median, as a fraction of it.

    0 means every month was identical. Used for confidence only — the figures
    the user reads come from the months themselves.
    """
    if not middle or len(values) < 2:
        return 1.0
    distances = [abs(value - middle) for value in values]
    return float(sum(distances) / len(distances) / middle)


def _confidence(spread, months_used):
    """How steady the baseline is, 0-100.

    Two things make a projection trustworthy: months that resemble each other,
    and enough of them. Neither alone is enough, so the score is the first
    scaled by the second.
    """
    steadiness = max(0.0, 1.0 - spread * 2.5)
    evidence = min(months_used / LOOKBACK_MONTHS, 1.0)
    return int(round(steadiness * (0.7 + 0.3 * evidence) * 100))


def complete_months(trends, today):
    """The months that have finished, oldest first.

    A month counts as complete once the calendar has moved past it. The month
    containing `today` never counts, even on its last day — being one day out
    on the conservative side is worth more than the edge case.
    """
    current = f"{today.year:04d}-{today.month:02d}"
    return [point for point in trends if point["month"] < current]


def forecast(trends, today=None, committed=None):
    """Project the month after the last complete one.

    `trends` is the monthly series from aggregations: {month, spent, income}.
    `committed` is the known recurring monthly commitment, if it has been
    computed — it is reported alongside, never added to the projection, because
    those payments are already inside the months the baseline is built from.
    """
    today = today or dt.date.today()
    finished = complete_months(trends, today)

    if len(finished) < MIN_MONTHS:
        return {
            "available": False,
            "reason": (
                f"A projection needs at least {MIN_MONTHS} complete months to "
                f"compare. There {'is' if len(finished) == 1 else 'are'} "
                f"{len(finished)} so far."
            ),
            "months_used": len(finished),
        }

    window = finished[-LOOKBACK_MONTHS:]
    spending = [_money(point["spent"]) for point in window]
    income = [_money(point["income"]) for point in window]

    middle = _median(spending)
    spread = _spread(spending, middle)

    return {
        "available": True,
        "reason": None,
        "month": _next_month(window[-1]["month"]),
        "months_used": len(window),
        "from_month": window[0]["month"],
        "to_month": window[-1]["month"],
        "projected_spending": middle,
        "projected_income": _median(income),
        "projected_net": _median(income) - middle,
        "spending_low": min(spending),
        "spending_high": max(spending),
        "committed": _money(committed) if committed else ZERO,
        "confidence": _confidence(spread, len(window)),
        "basis": (
            f"The middle of your last {len(window)} complete months "
            f"({window[0]['month']} to {window[-1]['month']}). "
            f"Those months ranged from {min(spending)} to {max(spending)}."
        ),
    }


def month_progress(trends, month, projected_spending, today=None):
    """How the month in progress is tracking against its projection.

    Returns None when the month has not started or is not in the data — an
    absent panel is better than one reporting zero spent so far.
    """
    today = today or dt.date.today()

    point = next((entry for entry in trends if entry["month"] == month), None)
    if point is None:
        return None

    spent = _money(point["spent"])
    projected = _money(projected_spending)

    return {
        "month": month,
        "spent_so_far": spent,
        "projected": projected,
        # Deliberately not extrapolated to a month-end figure. "You are on
        # track for ₹47,000" from six days of data is a guess wearing a
        # number's clothes.
        "share_of_projection": (
            int(round(float(spent / projected) * 100)) if projected else 0
        ),
        "remaining": max(ZERO, projected - spent),
    }
