"""Financial health, scored 0-100 from the user's own transactions.

Sits directly after s12_aggregations because it is built entirely on that
module's output — the suffix keeps the reading order intact without renumbering
everything downstream.

Every component below is arithmetic on real rows. There is no model here and
nothing is predicted, so the interface must present this as a summary of what
already happened, not a forecast or a rating.

Two honesty rules the scoring follows:

  - A component that cannot be computed is dropped and the weights are
    renormalised, rather than being scored 50 and quietly dragging the total
    toward the middle.
  - Below MIN_MONTHS of history the whole score is withheld. Two weeks of one
    statement cannot describe spending consistency, and a confident 82/100
    built on it would be worse than no score at all.
"""

from statistics import mean, pstdev

from app.store.s12_aggregations import monthly_trends, summary

# A score needs enough months to say anything about consistency over time.
MIN_MONTHS = 2

BANDS = [
    (80, "Excellent"),
    (65, "Good"),
    (50, "Fair"),
    (0, "Needs attention"),
]


def _clamp(value):
    return max(0.0, min(100.0, value))


def _consistency(values):
    """100 when every month is the same, falling as they scatter.

    Uses the coefficient of variation — spread relative to the average — so a
    household spending 50,000 a month is not judged inconsistent for varying by
    2,000 when one spending 5,000 would be.
    """
    usable = [value for value in values if value > 0]
    if len(usable) < 2:
        return None

    average = mean(usable)
    if average == 0:
        return None

    variation = pstdev(usable) / average
    # A CV of 0.5 (half the average) is treated as fully inconsistent.
    return _clamp((1 - variation / 0.5) * 100)


def _band(score):
    for floor, label in BANDS:
        if score >= floor:
            return label
    return BANDS[-1][1]


def financial_health(session, anomaly_total=0.0, **source):
    """Score the user's finances, or explain why it cannot be scored.

    `anomaly_total` is the rupee value of flagged spending in the period, which
    the caller already has from the anomalies endpoint — recomputing it here
    would mean running the detector twice per request.

    Returns {available, score, band, components, reason}. When `available` is
    false the UI shows `reason` instead of a number.
    """
    totals = summary(session, None, **source)
    trends = monthly_trends(session, **source)

    spent = float(totals["total_spent"])
    income = float(totals["total_income"])

    if len(trends) < MIN_MONTHS:
        return {
            "available": False,
            "score": None,
            "band": None,
            "components": [],
            "reason": (
                f"Needs at least {MIN_MONTHS} months of transactions to score. "
                f"You have {len(trends)}."
            ),
        }

    monthly_spend = [float(point["spent"]) for point in trends]
    monthly_income = [float(point["income"]) for point in trends]

    components = []

    # 1. Savings rate — the share of income that survived the month.
    if income > 0:
        rate = (income - spent) / income * 100
        components.append({
            "key": "savings_rate",
            "label": "Savings rate",
            # A 30% savings rate is treated as a full score.
            "value": round(_clamp(rate / 30 * 100)),
            "weight": 30,
            "detail": f"{rate:.1f}% of income not spent",
        })

    # 2. Budget discipline — months that ended with income ahead of spending.
    within = sum(
        1 for spend, earn in zip(monthly_spend, monthly_income) if earn >= spend
    )
    components.append({
        "key": "discipline",
        "label": "Budget discipline",
        "value": round(within / len(trends) * 100),
        "weight": 25,
        "detail": f"{within} of {len(trends)} months spent less than earned",
    })

    # 3. Spending consistency — predictable months are easier to plan around.
    consistency = _consistency(monthly_spend)
    if consistency is not None:
        components.append({
            "key": "consistency",
            "label": "Spending consistency",
            "value": round(consistency),
            "weight": 20,
            "detail": "how steady your monthly spending is",
        })

    # 4. Unusual spending — how much of the total came from flagged rows.
    if spent > 0:
        share = min(1.0, anomaly_total / spent)
        components.append({
            "key": "unusual",
            "label": "Unusual spending",
            # Inverted: less flagged spending is a better score.
            "value": round(_clamp((1 - share / 0.2) * 100)),
            "weight": 15,
            "detail": f"{share * 100:.1f}% of spending was flagged as unusual",
        })

    # 5. Income stability — irregular income makes everything else harder.
    income_stability = _consistency(monthly_income)
    if income_stability is not None:
        components.append({
            "key": "income_stability",
            "label": "Income stability",
            "value": round(income_stability),
            "weight": 10,
            "detail": "how steady your monthly income is",
        })

    if not components:
        return {
            "available": False,
            "score": None,
            "band": None,
            "components": [],
            "reason": "Not enough income or spending recorded to score.",
        }

    total_weight = sum(component["weight"] for component in components)
    score = round(
        sum(component["value"] * component["weight"] for component in components)
        / total_weight
    )

    return {
        "available": True,
        "score": score,
        "band": _band(score),
        "components": components,
        "reason": None,
    }
