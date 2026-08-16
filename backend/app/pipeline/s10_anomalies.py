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

# How far above the norm a transaction has to sit before it is worth showing.
#
# The default is 2.5 standard deviations. Lower means more transactions are
# flagged, not that the detection is better — someone whose spending is
# naturally erratic drowns at 2.0, and someone with very steady habits sees
# almost nothing at 3.0. It is a preference about how much noise is useful,
# which is why it belongs to the user rather than being fixed in the code.
SENSITIVITY = {
    "low": 3.0,      # only the genuinely extreme
    "medium": SIGMA, # the default
    "high": 2.0,     # more to review
}


def sigma_for(sensitivity=None) -> float:
    """The threshold multiplier for a named sensitivity, defaulting to medium."""
    return SENSITIVITY.get(str(sensitivity or "medium").lower(), SIGMA)
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


# --- explainable scoring ---------------------------------------------------
#
# The flag above answers "is this unusual". The score below answers "how
# unusual, and on what grounds" — the question a user actually has when they
# see a transaction singled out.
#
# It is a weighted blend of independent deviations rather than a model output.
# That matters: every number here traces back to arithmetic on the user's own
# transactions, so the UI can show the working rather than asking for trust.
# Nothing here is machine learning, and the interface must not call it that.

# How many multiples of the baseline count as "as unusual as it gets". Past
# this the factor saturates at 100 — the difference between 8x and 40x is not
# worth expressing, both are simply extreme.
_RATIO_CEILING = 5.0

# Same idea in standard deviations, for the amount factor.
_SIGMA_CEILING = 5.0

# Weights sum to 1 over whatever factors are available. A merchant with no
# history contributes nothing rather than a neutral 50, which would drag every
# score toward the middle and make the number useless.
_WEIGHTS = {
    "amount": 0.35,
    "category": 0.30,
    "merchant": 0.20,
    "frequency": 0.15,
}

# A merchant needs this much history before its own average means anything.
_MIN_MERCHANT_HISTORY = 3


def _percent(value):
    """Clamp to 0-100 and round. Every factor is reported on this scale."""
    return max(0, min(100, round(value)))


def score_transaction(amount, peers, merchant_amounts=None):
    """How unusual is `amount`, given its category peers? Returns a report.

    `peers` are the other amounts in the same category and window — the same
    set detect_anomalies() builds its baseline from, with this transaction
    already excluded. `merchant_amounts` are this merchant's other amounts, if
    there are any.

    Returns {score, factors, baseline, ratio} where score is 0-100 and factors
    is a list of {key, label, value, detail} ready to render. A caller with too
    little history gets a score of 0 and an empty factor list rather than a
    confident-looking number built on two data points.
    """
    amount = float(amount)
    peers = [float(value) for value in peers if value is not None]

    if not peers:
        return {"score": 0, "factors": [], "baseline": None, "ratio": None}

    baseline = mean(peers)
    spread = pstdev(peers)
    ratio = amount / baseline if baseline else 0

    factors = []

    # 1. Amount — how many standard deviations above the category's own spread.
    if spread > 0:
        sigmas = (amount - baseline) / spread
        factors.append({
            "key": "amount",
            "label": "Amount deviation",
            "value": _percent(sigmas / _SIGMA_CEILING * 100),
            "detail": f"{sigmas:.1f} standard deviations above the category average",
        })
    else:
        # Every past amount identical — a fixed subscription. Sigma cannot
        # speak, so fall back to the plain ratio.
        factors.append({
            "key": "amount",
            "label": "Amount deviation",
            "value": _percent((ratio - 1) / (_RATIO_CEILING - 1) * 100),
            "detail": "every previous amount in this category was identical",
        })

    # 2. Category — the plain multiple, which is what the user reads.
    factors.append({
        "key": "category",
        "label": "Category deviation",
        "value": _percent((ratio - 1) / (_RATIO_CEILING - 1) * 100),
        "detail": f"{ratio:.1f}x the category average",
    })

    # 3. Merchant — only when this merchant has enough of its own history.
    merchant_amounts = [float(value) for value in (merchant_amounts or [])]
    if len(merchant_amounts) >= _MIN_MERCHANT_HISTORY:
        merchant_baseline = mean(merchant_amounts)
        merchant_ratio = amount / merchant_baseline if merchant_baseline else 0
        factors.append({
            "key": "merchant",
            "label": "Merchant deviation",
            "value": _percent((merchant_ratio - 1) / (_RATIO_CEILING - 1) * 100),
            "detail": (
                f"{merchant_ratio:.1f}x what you usually pay this merchant "
                f"({_format_inr(merchant_baseline)} across "
                f"{len(merchant_amounts)} transactions)"
            ),
        })

    # 4. Frequency — a merchant you rarely use is more notable than a regular.
    #    Seen never before scores 100, once 50, three times 25.
    seen = len(merchant_amounts)
    factors.append({
        "key": "frequency",
        "label": "Frequency deviation",
        "value": _percent(100 / (1 + seen)),
        "detail": (
            "no other transactions with this merchant in the period"
            if seen == 0
            else f"{seen} other transaction{'s' if seen != 1 else ''} with this merchant"
        ),
    })

    # Weighted mean over the factors that were actually available.
    total_weight = sum(_WEIGHTS[factor["key"]] for factor in factors)
    score = sum(factor["value"] * _WEIGHTS[factor["key"]] for factor in factors)

    return {
        "score": _percent(score / total_weight if total_weight else 0),
        "factors": factors,
        "baseline": round(baseline, 2),
        "ratio": round(ratio, 2) if baseline else None,
    }


def detect_anomalies(transactions, today=None, sensitivity=None):
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
        sigma = sigma_for(sensitivity)
        threshold = baseline + sigma * spread if spread > 0 else baseline * 1.5

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
