"""Plain-English observations about a set of transactions (PRD Part 6).

Every sentence here is generated from a number that was already computed, and
every one carries the comparison it is based on. That is the difference between
an insight and a slogan: "food spending rose 32%" is only useful next to what
it rose from and over what period.

Rules this module follows:

  - Nothing is emitted without enough data behind it. A month-on-month change
    needs two months; a "largest category" needs a category with spending.
  - No advice. "You spent 32% more on food" is an observation. "You should
    spend less on food" is guidance this project is not qualified to give, and
    the PRD explicitly rules it out.
  - Every insight names its own evidence, so the UI can show the working.
"""

# A change smaller than this is noise, not news.
MIN_CHANGE_PERCENT = 5


_MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _pct(current, previous):
    if not previous:
        return None
    return (current - previous) / previous * 100


def _month(key):
    """'2026-09' -> 'Sep 2026'.

    The rest of the app shows months this way. A sentence meant to be read
    should not be the one place a raw sort key surfaces.
    """
    try:
        year, month = key.split("-")
        return f"{_MONTH_NAMES[int(month) - 1]} {year}"
    except (ValueError, IndexError, AttributeError):
        # An unexpected key is not worth an exception in a display helper.
        return key


def _merchant(name):
    """Merchant names arrive lowercased from the normalized narration.

    Title-casing here rather than at the source keeps the grouping key stable —
    two spellings of one merchant must still land in the same bucket.
    """
    if not name:
        return "This merchant"
    return name[0].upper() + name[1:]


def build_insights(summary, trends, anomalies=None, recurring=None):
    """Observations worth showing, most useful first.

    Each is {key, tone, headline, detail}. `tone` is 'neutral', 'positive' or
    'warning' — used for colour only, never to imply a judgement the numbers
    do not support.
    """
    insights = []
    anomalies = anomalies or []
    recurring = recurring or []

    spent = float(summary.get("total_spent") or 0)
    income = float(summary.get("total_income") or 0)
    by_category = summary.get("by_category") or []
    merchants = summary.get("top_merchants") or []

    # --- month on month -----------------------------------------------------
    if len(trends) >= 2:
        latest = trends[-1]
        previous = trends[-2]
        change = _pct(float(latest["spent"]), float(previous["spent"]))

        if change is not None and abs(change) >= MIN_CHANGE_PERCENT:
            rising = change > 0
            insights.append({
                "key": "spend_change",
                "tone": "warning" if rising else "positive",
                "headline": (
                    f"Spending {'increased' if rising else 'decreased'} "
                    f"{abs(change):.0f}% last month"
                ),
                "detail": (
                    f"{format_money(latest['spent'])} in {_month(latest['month'])}, "
                    f"against {format_money(previous['spent'])} in "
                    f"{_month(previous['month'])}."
                ),
            })

    # --- biggest category ---------------------------------------------------
    if by_category and spent > 0:
        top = by_category[0]
        share = float(top["total"]) / spent * 100
        insights.append({
            "key": "top_category",
            "tone": "neutral",
            "headline": (
                f"{format_category(top['category'])} is your largest spending category"
            ),
            "detail": (
                f"{format_money(top['total'])} across {top['count']} transactions — "
                f"{share:.0f}% of everything you spent."
            ),
        })

    # --- concentration ------------------------------------------------------
    if len(by_category) >= 3 and spent > 0:
        top_three = sum(float(row["total"]) for row in by_category[:3])
        share = top_three / spent * 100
        if share >= 60:
            insights.append({
                "key": "concentration",
                "tone": "neutral",
                "headline": f"Three categories account for {share:.0f}% of spending",
                "detail": (
                    ", ".join(format_category(row["category"]) for row in by_category[:3])
                    + " together come to "
                    + format_money(top_three)
                    + "."
                ),
            })

    # --- savings ------------------------------------------------------------
    if income > 0:
        rate = (income - spent) / income * 100
        insights.append({
            "key": "savings_rate",
            "tone": "positive" if rate >= 20 else "warning" if rate < 0 else "neutral",
            "headline": (
                f"You kept {rate:.0f}% of your income"
                if rate >= 0
                else f"You spent {abs(rate):.0f}% more than you earned"
            ),
            "detail": (
                f"{format_money(income)} in, {format_money(spent)} out, over "
                f"{len(trends)} month{'s' if len(trends) != 1 else ''}."
            ),
        })

    # --- busiest month ------------------------------------------------------
    if len(trends) >= 3:
        peak = max(trends, key=lambda point: float(point["spent"]))
        average = sum(float(point["spent"]) for point in trends) / len(trends)
        if average and float(peak["spent"]) > average * 1.3:
            insights.append({
                "key": "peak_month",
                "tone": "neutral",
                "headline": f"{_month(peak['month'])} was your heaviest month",
                "detail": (
                    f"{format_money(peak['spent'])}, against a monthly average of "
                    f"{format_money(average)}."
                ),
            })

    # --- top merchant -------------------------------------------------------
    if merchants and spent > 0:
        top = merchants[0]
        insights.append({
            "key": "top_merchant",
            "tone": "neutral",
            "headline": f"You spent the most at {_merchant(top['merchant'])}",
            "detail": (
                f"{format_money(top['total'])} across {top['count']} transactions."
            ),
        })

    # --- flagged ------------------------------------------------------------
    if anomalies:
        total = sum(float(row["amount"]) for row in anomalies)
        insights.append({
            "key": "anomalies",
            "tone": "warning",
            "headline": (
                f"{len(anomalies)} transaction"
                f"{'s' if len(anomalies) != 1 else ''} stand out as unusual"
            ),
            "detail": (
                f"{format_money(total)} in total, each far above the usual for its "
                f"category. Unusual does not mean wrong."
            ),
        })

    # --- recurring ----------------------------------------------------------
    confident = [row for row in recurring if row["confidence"] >= 60]
    if confident:
        insights.append({
            "key": "recurring",
            "tone": "neutral",
            "headline": (
                f"{len(confident)} recurring payment"
                f"{'s' if len(confident) != 1 else ''} detected"
            ),
            "detail": (
                "Regular payments to "
                + ", ".join(row["merchant"] for row in confident[:3])
                + ("," if len(confident) > 3 else "")
                + (f" and {len(confident) - 3} more." if len(confident) > 3 else ".")
            ),
        })

    return insights


def format_money(value):
    """Indian digit grouping, whole rupees. Display only.

    Public because s10f_story writes the same sentences about the same figures;
    two copies of this would eventually disagree about a comma.
    """
    number = float(value)
    sign = "-" if number < 0 else ""
    whole = f"{abs(number):,.0f}"

    # en-IN grouping: last three digits, then pairs.
    digits = whole.replace(",", "")
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])

    return f"{sign}Rs {whole}"


def format_category(category):
    if category == "bills_utilities":
        return "Bills & utilities"
    return category.replace("_", " ").capitalize()
