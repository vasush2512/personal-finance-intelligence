"""Recurring payments (PRD Part 9).

A subscription, a rent payment and a monthly premium all look the same in a
statement: the same merchant, for about the same amount, at about the same
interval. This finds that shape and says how confident it is.

Two things it deliberately does not do:

  - It does not predict a date it cannot support. A next-payment estimate is
    only returned when the intervals are regular enough for one to mean
    anything, and the confidence travels with it.
  - It does not treat "seen three times" as recurring on its own. Three trips
    to the same restaurant are not a subscription; what makes a payment
    recurring is the regularity of the gaps, not the count.
"""

from collections import defaultdict
from statistics import mean, median, pstdev

# Three payments give two gaps, which is the fewest that can show a rhythm.
MIN_OCCURRENCES = 3

# Named periods, with the tolerance either side that still counts as that
# period. Monthly is the widest because month lengths differ by three days and
# billing dates drift over weekends.
_PERIODS = [
    ("Weekly", 7, 2),
    ("Fortnightly", 14, 3),
    ("Monthly", 30, 6),
    ("Quarterly", 91, 12),
    ("Half-yearly", 182, 20),
    ("Yearly", 365, 30),
]

# Above this, the gaps are too irregular to call the payment recurring at all.
MAX_GAP_VARIATION = 0.35


def _classify(gap_days):
    """Name the rhythm, or None when it matches no familiar period."""
    for name, length, tolerance in _PERIODS:
        if abs(gap_days - length) <= tolerance:
            return name
    return None


def _variation(values):
    """Spread relative to the average. 0 means perfectly regular."""
    if len(values) < 2:
        return 0.0
    average = mean(values)
    return pstdev(values) / average if average else 1.0


def find_recurring(transactions, today=None):
    """Merchants being paid on a regular rhythm, most confident first.

    `transactions` are dicts with date (a date), amount (float), merchant,
    category and direction. Only debits are considered: an employer paying a
    salary every month is regular, but it is not a recurring payment the user
    makes.
    """
    by_merchant = defaultdict(list)
    for txn in transactions:
        if txn.get("direction") != "debit":
            continue
        by_merchant[txn["merchant"]].append(txn)

    results = []

    for merchant, rows in by_merchant.items():
        if len(rows) < MIN_OCCURRENCES:
            continue

        rows.sort(key=lambda row: row["date"])
        gaps = [
            (rows[index + 1]["date"] - rows[index]["date"]).days
            for index in range(len(rows) - 1)
        ]
        # Same-day repeats are duplicates, not a rhythm — see s10b_duplicates.
        gaps = [gap for gap in gaps if gap > 0]
        if len(gaps) < MIN_OCCURRENCES - 1:
            continue

        typical_gap = median(gaps)
        gap_variation = _variation(gaps)
        if gap_variation > MAX_GAP_VARIATION:
            continue

        frequency = _classify(typical_gap)
        if frequency is None:
            continue

        amounts = [float(row["amount"]) for row in rows]
        amount_variation = _variation(amounts)

        # Confidence is regularity first, then how steady the amount is, then
        # how much evidence there is. A four-year-old yearly payment seen four
        # times is more convincing than a monthly one seen three.
        regularity = max(0.0, 1 - gap_variation / MAX_GAP_VARIATION)
        steadiness = max(0.0, 1 - min(amount_variation, 0.5) / 0.5)
        evidence = min(1.0, (len(rows) - MIN_OCCURRENCES + 1) / 6)

        confidence = round(
            (regularity * 0.5 + steadiness * 0.3 + evidence * 0.2) * 100
        )

        last = rows[-1]
        results.append({
            "merchant": merchant,
            "category": last.get("category"),
            "frequency": frequency,
            "typical_gap_days": int(typical_gap),
            "occurrences": len(rows),
            "average_amount": round(mean(amounts), 2),
            "last_amount": round(float(last["amount"]), 2),
            "last_date": last["date"],
            # Only offered when the rhythm is regular enough to mean something.
            # A date attached to a 40%-confident guess reads as a commitment.
            "next_expected": (
                last["date"] + _timedelta(int(typical_gap))
                if confidence >= 60
                else None
            ),
            "confidence": confidence,
            "amount_varies": amount_variation > 0.1,
        })

    results.sort(key=lambda row: (-row["confidence"], -row["average_amount"]))
    return results


def _timedelta(days):
    from datetime import timedelta

    return timedelta(days=days)


def monthly_commitment(recurring):
    """Roughly what the recurring payments cost per month, in rupees.

    Everything is normalised to a monthly figure so a yearly premium and a
    monthly subscription can be added together honestly. Low-confidence rows
    are left out rather than inflating a number the user might budget against.
    """
    total = 0.0
    for row in recurring:
        if row["confidence"] < 60:
            continue
        gap = row["typical_gap_days"] or 30
        total += row["average_amount"] * (30 / gap)
    return round(total, 2)
