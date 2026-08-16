"""Duplicate and recurring detection, and the insight generator (Phase 2).

All pure functions over plain dicts, so none of this needs a database.
"""

import datetime as dt

from app.pipeline.s10b_duplicates import MAX_DAY_GAP, find_duplicates
from app.pipeline.s10c_recurring import (
    MIN_OCCURRENCES,
    find_recurring,
    monthly_commitment,
)
from app.pipeline.s10d_insights import build_insights


def txn(day, amount, merchant, direction="debit", identifier=None, method="UPI"):
    return {
        "id": identifier if identifier is not None else day * 1000 + int(amount),
        "date": dt.date(2026, 6, day),
        "amount": float(amount),
        "merchant": merchant,
        "direction": direction,
        "payment_method": method,
        "category": "food",
    }


# --- duplicates -----------------------------------------------------------


def test_same_amount_same_merchant_same_day_is_a_strong_candidate():
    pairs = find_duplicates([txn(4, 450, "Swiggy", identifier=1),
                             txn(4, 450, "Swiggy", identifier=2)])
    assert len(pairs) == 1
    assert pairs[0]["score"] == 100
    assert "Same day" in pairs[0]["reasons"]


def test_a_settlement_a_day_later_is_still_flagged():
    pairs = find_duplicates([txn(4, 450, "Swiggy", identifier=1),
                             txn(5, 450, "Swiggy", identifier=2)])
    assert len(pairs) == 1
    assert pairs[0]["days_apart"] == 1
    assert "1 day apart" in pairs[0]["reasons"]


def test_a_gap_wider_than_the_window_is_not_a_duplicate():
    """Same shop, same price, a week later — that is lunch again."""
    pairs = find_duplicates([txn(4, 450, "Swiggy", identifier=1),
                             txn(4 + MAX_DAY_GAP + 3, 450, "Swiggy", identifier=2)])
    assert pairs == []


def test_different_amounts_are_never_paired():
    pairs = find_duplicates([txn(4, 450, "Swiggy", identifier=1),
                             txn(4, 451, "Swiggy", identifier=2)])
    assert pairs == []


def test_different_merchants_are_never_paired():
    pairs = find_duplicates([txn(4, 450, "Swiggy", identifier=1),
                             txn(4, 450, "Zomato", identifier=2)])
    assert pairs == []


def test_a_debit_and_a_credit_are_not_a_duplicate():
    """A refund matching a charge is the opposite of a double charge."""
    pairs = find_duplicates([
        txn(4, 450, "Amazon", direction="debit", identifier=1),
        txn(4, 450, "Amazon", direction="credit", identifier=2),
    ])
    assert pairs == []


def test_three_identical_rows_produce_every_pairing():
    rows = [txn(4, 450, "Swiggy", identifier=i) for i in (1, 2, 3)]
    assert len(find_duplicates(rows)) == 3


def test_results_are_strongest_first():
    rows = [
        txn(4, 450, "Swiggy", identifier=1),
        txn(6, 450, "Swiggy", identifier=2),   # 2 days apart, weaker
        txn(10, 900, "Zomato", identifier=3),
        txn(10, 900, "Zomato", identifier=4),  # same day, stronger
    ]
    pairs = find_duplicates(rows)
    assert pairs[0]["score"] >= pairs[-1]["score"]


def test_the_limit_is_respected():
    rows = [txn(4, 450, "Swiggy", identifier=i) for i in range(6)]
    assert len(find_duplicates(rows, limit=3)) == 3


# --- recurring ------------------------------------------------------------


def monthly(merchant, amount, count=6, start=dt.date(2026, 1, 5), gap=30):
    return [
        {
            "date": start + dt.timedelta(days=gap * index),
            "amount": float(amount),
            "merchant": merchant,
            "direction": "debit",
            "category": "entertainment",
        }
        for index in range(count)
    ]


def test_a_monthly_subscription_is_detected():
    found = find_recurring(monthly("Netflix", 649))
    assert len(found) == 1
    assert found[0]["frequency"] == "Monthly"
    assert found[0]["merchant"] == "Netflix"
    assert found[0]["confidence"] > 70


def test_too_few_occurrences_is_not_recurring():
    found = find_recurring(monthly("Netflix", 649, count=MIN_OCCURRENCES - 1))
    assert found == []


def test_irregular_gaps_are_not_recurring():
    """Three visits to a restaurant are not a subscription."""
    rows = monthly("Dhaba", 400, count=5)
    rows[1]["date"] = rows[0]["date"] + dt.timedelta(days=2)
    rows[2]["date"] = rows[0]["date"] + dt.timedelta(days=51)
    rows[3]["date"] = rows[0]["date"] + dt.timedelta(days=57)
    assert find_recurring(rows) == []


def test_income_is_not_a_recurring_payment():
    """A salary arriving monthly is regular, but the user is not paying it."""
    rows = monthly("Employer", 80000)
    for row in rows:
        row["direction"] = "credit"
    assert find_recurring(rows) == []


def test_weekly_and_yearly_rhythms_are_named():
    assert find_recurring(monthly("Milk", 60, count=8, gap=7))[0]["frequency"] == "Weekly"
    assert find_recurring(monthly("Domain", 900, count=4, gap=365))[0]["frequency"] == "Yearly"


def test_a_next_date_is_offered_only_when_confident():
    confident = find_recurring(monthly("Netflix", 649, count=8))[0]
    assert confident["confidence"] >= 60
    assert confident["next_expected"] is not None
    # A month after the last one, give or take the tolerance.
    assert confident["next_expected"] > confident["last_date"]


def test_a_varying_amount_is_marked_as_varying():
    rows = monthly("Electricity", 1000, count=6)
    for index, row in enumerate(rows):
        row["amount"] = 1000 + index * 260
    found = find_recurring(rows)
    assert found and found[0]["amount_varies"] is True


def test_monthly_commitment_normalises_periods():
    """A yearly payment must not be counted at its full value every month."""
    yearly = find_recurring(monthly("Domain", 1200, count=4, gap=365))
    total = monthly_commitment(yearly)
    assert 80 < total < 120  # about 1200/12


# --- insights -------------------------------------------------------------


BASE_SUMMARY = {
    "total_spent": "50000.00",
    "total_income": "80000.00",
    "by_category": [
        {"category": "food", "total": "20000.00", "count": 40},
        {"category": "rent", "total": "18000.00", "count": 2},
        {"category": "transport", "total": "7000.00", "count": 15},
    ],
    "top_merchants": [{"merchant": "Swiggy", "total": "9000.00", "count": 22}],
}


def test_no_month_comparison_without_two_months():
    insights = build_insights(BASE_SUMMARY, [{"month": "2026-06", "spent": "50000.00", "income": "80000.00"}])
    assert not any(item["key"] == "spend_change" for item in insights)


def test_a_month_on_month_rise_is_reported():
    trends = [
        {"month": "2026-05", "spent": "40000.00", "income": "80000.00"},
        {"month": "2026-06", "spent": "50000.00", "income": "80000.00"},
    ]
    insights = build_insights(BASE_SUMMARY, trends)
    change = next(item for item in insights if item["key"] == "spend_change")
    assert "increased" in change["headline"]
    assert "25%" in change["headline"]


def test_a_change_too_small_to_matter_is_not_reported():
    trends = [
        {"month": "2026-05", "spent": "50000.00", "income": "80000.00"},
        {"month": "2026-06", "spent": "50500.00", "income": "80000.00"},
    ]
    insights = build_insights(BASE_SUMMARY, trends)
    assert not any(item["key"] == "spend_change" for item in insights)


def test_the_biggest_category_is_named_with_its_share():
    insights = build_insights(BASE_SUMMARY, [])
    top = next(item for item in insights if item["key"] == "top_category")
    assert "Food" in top["headline"]
    assert "40%" in top["detail"]


def test_overspending_is_stated_plainly():
    summary = {**BASE_SUMMARY, "total_spent": "100000.00", "total_income": "80000.00"}
    insights = build_insights(summary, [])
    savings = next(item for item in insights if item["key"] == "savings_rate")
    assert "more than you earned" in savings["headline"]
    assert savings["tone"] == "warning"


def test_months_are_written_the_way_they_are_read():
    """'2026-09' is a sort key. A sentence should say 'Sep 2026'."""
    trends = [
        {"month": "2026-08", "spent": "40000.00", "income": "80000.00"},
        {"month": "2026-09", "spent": "50000.00", "income": "80000.00"},
    ]
    change = next(
        item for item in build_insights(BASE_SUMMARY, trends)
        if item["key"] == "spend_change"
    )
    assert "Sep 2026" in change["detail"]
    assert "Aug 2026" in change["detail"]
    assert "2026-09" not in change["detail"]


def test_a_merchant_never_opens_a_sentence_in_lower_case():
    """Merchants arrive lowercased from the normalized narration."""
    summary = {
        **BASE_SUMMARY,
        "top_merchants": [{"merchant": "swiggy", "total": "9000.00", "count": 22}],
    }
    top = next(
        item for item in build_insights(summary, [])
        if item["key"] == "top_merchant"
    )
    assert "Swiggy" in top["headline"]
    assert "swiggy" not in top["headline"]


def test_every_insight_carries_evidence():
    trends = [
        {"month": "2026-05", "spent": "40000.00", "income": "80000.00"},
        {"month": "2026-06", "spent": "50000.00", "income": "80000.00"},
    ]
    for item in build_insights(BASE_SUMMARY, trends):
        assert item["headline"] and item["detail"]
        assert item["tone"] in {"neutral", "positive", "warning"}
