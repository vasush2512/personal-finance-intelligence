"""Near-duplicate transactions (PRD Part 8).

Exact duplicates never reach the database: the fingerprint in s05_normalize is
a hash of date|normalized_description|amount|direction, and its unique index
drops them at import. What survives that check is the harder case — the same
payment recorded twice with something slightly different about it:

  - a card payment that settles a day or two after it was authorised
  - a statement re-exported with a shifted value date
  - a merchant whose narration carries a different reference each time

So this looks for pairs that are the same amount and merchant within a few
days, and scores how likely they are to be one payment rather than two.

Nothing is deleted, and nothing is hidden. Two ₹40 chai payments on the same
morning are genuinely two transactions, and only the person who made them
knows. The output is a suggestion with its reasons attached.
"""

from collections import defaultdict
from datetime import date

# How far apart two records of the same payment can plausibly sit. Three days
# covers weekend settlement; beyond that a repeat is more likely a real repeat.
MAX_DAY_GAP = 3

# Below this, the pair is not worth showing. Tuned so that "same amount, same
# merchant, different day" (75) surfaces and nothing weaker does.
REPORT_THRESHOLD = 70

# Points awarded. Same amount and merchant is the floor for a candidate; the
# rest sharpen it. They sum to 100 for a same-day, same-method pair.
_BASE = 60
_SAME_DAY = 25
_SAME_METHOD = 15


def _score(first, second):
    """How likely are these two records the same payment? 0-100 with reasons."""
    score = _BASE
    reasons = ["Same amount", "Same merchant"]

    gap = abs((first["date"] - second["date"]).days)
    if gap == 0:
        score += _SAME_DAY
        reasons.append("Same day")
    else:
        # Partial credit that decays with distance: one day apart is far more
        # suspicious than three.
        score += int(_SAME_DAY * (1 - gap / (MAX_DAY_GAP + 1)))
        reasons.append(f"{gap} day{'s' if gap != 1 else ''} apart")

    if (
        first.get("payment_method")
        and first.get("payment_method") == second.get("payment_method")
    ):
        score += _SAME_METHOD
        reasons.append(f"Both {first['payment_method']}")

    return min(100, score), reasons


def find_duplicates(transactions, threshold=REPORT_THRESHOLD, limit=None):
    """Pairs that look like one payment recorded twice, strongest first.

    `transactions` are dicts with id, date (a date), amount (float), direction,
    merchant and optionally payment_method.

    Bucketed by (amount, direction, merchant) before any comparison. Comparing
    every row against every other is quadratic and unusable at a hundred
    thousand rows; two transactions that differ in amount or merchant can never
    be a pair here, so the bucket key does the elimination for free.
    """
    buckets = defaultdict(list)
    for txn in transactions:
        key = (round(float(txn["amount"]), 2), txn["direction"], txn["merchant"])
        buckets[key].append(txn)

    pairs = []
    for group in buckets.values():
        if len(group) < 2:
            continue

        # Sorted so the inner loop can stop as soon as the gap is too wide,
        # rather than walking the rest of a large bucket.
        group.sort(key=lambda row: row["date"])

        for index, first in enumerate(group):
            for second in group[index + 1:]:
                gap = (second["date"] - first["date"]).days
                if gap > MAX_DAY_GAP:
                    break

                score, reasons = _score(first, second)
                if score < threshold:
                    continue

                pairs.append({
                    "score": score,
                    "reasons": reasons,
                    "amount": first["amount"],
                    "merchant": first["merchant"],
                    "direction": first["direction"],
                    "days_apart": gap,
                    "first": first,
                    "second": second,
                })

    pairs.sort(key=lambda pair: (-pair["score"], -_as_ordinal(pair["second"]["date"])))
    return pairs[:limit] if limit else pairs


def _as_ordinal(value):
    """Sort key that works whether the caller passed a date or an ISO string."""
    return value.toordinal() if isinstance(value, date) else 0
