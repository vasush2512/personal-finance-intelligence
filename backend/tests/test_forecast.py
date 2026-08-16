"""Cash flow projection (Phase 3).

Pure arithmetic over the monthly series, so none of this needs a database.
"""

import datetime as dt
from decimal import Decimal

from app.pipeline.s10e_forecast import (
    LOOKBACK_MONTHS,
    MIN_MONTHS,
    complete_months,
    forecast,
    month_progress,
)

TODAY = dt.date(2026, 8, 14)


def months(*pairs):
    """('2026-05', 40000) ... -> the trend series aggregations returns."""
    return [
        {"month": month, "spent": str(spent), "income": "80000.00"}
        for month, spent in pairs
    ]


# --- what counts as a month -----------------------------------------------


def test_the_month_in_progress_is_never_part_of_the_baseline():
    """Averaging in a half-finished month is how a forecast reads low."""
    trends = months(("2026-06", 40000), ("2026-07", 42000), ("2026-08", 3000))
    finished = complete_months(trends, TODAY)
    assert [point["month"] for point in finished] == ["2026-06", "2026-07"]


def test_future_dated_months_are_not_complete_either():
    trends = months(("2026-06", 40000), ("2026-09", 41000))
    assert [p["month"] for p in complete_months(trends, TODAY)] == ["2026-06"]


def test_too_few_months_returns_a_reason_not_a_number():
    result = forecast(months(("2026-06", 40000), ("2026-07", 42000)), today=TODAY)
    assert result["available"] is False
    assert "projected_spending" not in result
    assert str(MIN_MONTHS) in result["reason"]


def test_the_baseline_stops_at_the_lookback():
    trends = months(*[(f"2026-{m:02d}", 40000) for m in range(1, 8)])
    result = forecast(trends, today=TODAY)
    assert result["months_used"] == LOOKBACK_MONTHS


# --- the projection itself -------------------------------------------------


def test_steady_months_project_to_the_same_figure():
    trends = months(("2026-04", 40000), ("2026-05", 40000), ("2026-06", 40000))
    result = forecast(trends, today=TODAY)
    assert result["projected_spending"] == Decimal("40000.00")
    assert result["confidence"] > 80


def test_one_unusual_month_does_not_move_the_baseline_much():
    """The median exists for exactly this case."""
    steady = months(("2026-03", 40000), ("2026-04", 40000), ("2026-05", 40000))
    spike = steady + months(("2026-06", 250000))

    assert forecast(spike, today=TODAY)["projected_spending"] == Decimal("40000.00")


def test_the_range_is_the_real_smallest_and_largest():
    trends = months(("2026-04", 30000), ("2026-05", 40000), ("2026-06", 55000))
    result = forecast(trends, today=TODAY)
    assert result["spending_low"] == Decimal("30000.00")
    assert result["spending_high"] == Decimal("55000.00")
    assert result["spending_low"] <= result["projected_spending"] <= result["spending_high"]


def test_erratic_months_are_projected_with_low_confidence():
    steady = forecast(
        months(("2026-04", 40000), ("2026-05", 41000), ("2026-06", 39500)),
        today=TODAY,
    )
    erratic = forecast(
        months(("2026-04", 8000), ("2026-05", 74000), ("2026-06", 31000)),
        today=TODAY,
    )
    assert erratic["confidence"] < steady["confidence"]


def test_the_projected_month_follows_the_last_complete_one():
    trends = months(("2026-04", 40000), ("2026-05", 40000), ("2026-06", 40000))
    assert forecast(trends, today=TODAY)["month"] == "2026-07"


def test_december_rolls_into_january():
    trends = months(("2025-10", 40000), ("2025-11", 40000), ("2025-12", 40000))
    assert forecast(trends, today=dt.date(2026, 1, 9))["month"] == "2026-01"


def test_the_basis_names_the_months_it_used():
    trends = months(("2026-04", 40000), ("2026-05", 40000), ("2026-06", 40000))
    basis = forecast(trends, today=TODAY)["basis"]
    assert "2026-04" in basis and "2026-06" in basis
    assert "3 complete months" in basis


def test_commitments_are_reported_but_never_added_to_the_projection():
    """Recurring payments are already inside the months being averaged."""
    trends = months(("2026-04", 40000), ("2026-05", 40000), ("2026-06", 40000))
    result = forecast(trends, today=TODAY, committed=Decimal("2489.00"))
    assert result["committed"] == Decimal("2489.00")
    assert result["projected_spending"] == Decimal("40000.00")


# --- tracking the month in progress ----------------------------------------


def test_progress_reports_what_has_actually_been_spent():
    trends = months(("2026-07", 40000), ("2026-08", 12000))
    progress = month_progress(trends, "2026-08", Decimal("40000.00"), today=TODAY)
    assert progress["spent_so_far"] == Decimal("12000.00")
    assert progress["share_of_projection"] == 30
    assert progress["remaining"] == Decimal("28000.00")


def test_progress_past_the_projection_never_goes_negative():
    trends = months(("2026-08", 52000))
    progress = month_progress(trends, "2026-08", Decimal("40000.00"), today=TODAY)
    assert progress["remaining"] == Decimal("0.00")
    assert progress["share_of_projection"] == 130


def test_a_month_with_no_rows_yet_has_no_progress_panel():
    assert month_progress(months(("2026-07", 40000)), "2026-08", Decimal("1"), today=TODAY) is None
