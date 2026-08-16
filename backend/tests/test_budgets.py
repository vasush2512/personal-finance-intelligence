"""Monthly budgets.

Two things these exist to protect: that a budget's spending figure comes from
the same place the dashboard's does, and that the app never turns a limit into
a judgement.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s03_db import Base
from app.core.s04_models import Transaction, User
from app.store import s12_aggregations as aggregations
from app.store.s11b_categories import create_category
from app.store.s12f_budgets import (
    BudgetError,
    budget_progress,
    delete_budget,
    list_budgets,
    set_budget,
    update_budget,
)

TODAY = dt.date(2026, 8, 17)
MONTH = "2026-08"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


@pytest.fixture
def user(session):
    account = User(email="a@example.com", display_name="A", password_hash="x")
    session.add(account)
    session.commit()
    return account


def spend(session, user, amount, category, day=5, counter=[0]):
    counter[0] += 1
    session.add(Transaction(
        user_id=user.id,
        date=dt.date(2026, 8, day),
        description=f"ROW {counter[0]}",
        normalized_description=f"row {counter[0]}",
        amount=Decimal(amount),
        direction="debit",
        category=category,
        fingerprint=f"fp-{counter[0]}",
    ))
    session.commit()


# --- setting limits --------------------------------------------------------


def test_a_budget_is_stored(session, user):
    budget = set_budget(session, user.id, "food", "8000")
    assert budget.amount == Decimal("8000.00")
    assert budget.active is True


def test_setting_the_same_category_twice_replaces_the_limit(session, user):
    """There is one question — what is my limit for food — and one answer."""
    set_budget(session, user.id, "food", "8000")
    set_budget(session, user.id, "food", "9500")

    budgets = list_budgets(session, user.id)
    assert len(budgets) == 1
    assert budgets[0].amount == Decimal("9500.00")


def test_zero_and_negative_limits_are_refused(session, user):
    for bad in ("0", "-100"):
        with pytest.raises(BudgetError, match="more than zero"):
            set_budget(session, user.id, "food", bad)


def test_a_nonsense_limit_is_refused(session, user):
    with pytest.raises(BudgetError):
        set_budget(session, user.id, "food", "lots")


def test_an_unknown_category_cannot_have_a_budget(session, user):
    with pytest.raises(BudgetError):
        set_budget(session, user.id, "u_not_mine", "500")


def test_a_custom_category_can_have_a_budget(session, user):
    gym = create_category(session, user.id, "Gym")
    budget = set_budget(session, user.id, gym.key, "1500")
    assert budget.category == "u_gym"


def test_a_budget_can_be_paused_and_resumed(session, user):
    budget = set_budget(session, user.id, "food", "8000")

    update_budget(session, user.id, budget.id, active=False)
    assert budget_progress(session, user.id, month=MONTH, today=TODAY)["available"] is False

    update_budget(session, user.id, budget.id, active=True)
    assert budget_progress(session, user.id, month=MONTH, today=TODAY)["available"] is True


def test_deleting_a_budget_touches_no_transaction(session, user):
    spend(session, user, "500", "food")
    budget = set_budget(session, user.id, "food", "8000")

    assert delete_budget(session, user.id, budget.id) is True
    assert session.query(Transaction).count() == 1


# --- ownership -------------------------------------------------------------


def test_one_user_cannot_touch_anothers_budget(session, user):
    other = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(other)
    session.commit()

    budget = set_budget(session, user.id, "food", "8000")

    assert list_budgets(session, other.id) == []
    assert update_budget(session, other.id, budget.id, amount="1") is None
    assert delete_budget(session, other.id, budget.id) is False


def test_progress_counts_only_its_owners_spending(session, user):
    other = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(other)
    session.commit()

    set_budget(session, user.id, "food", "8000")
    session.add(Transaction(
        user_id=other.id, date=dt.date(2026, 8, 5), description="THEIRS",
        normalized_description="theirs", amount=Decimal("7000.00"),
        direction="debit", category="food", fingerprint="theirs-1",
    ))
    session.commit()

    item = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]
    assert item["spent"] == Decimal("0.00")


# --- progress --------------------------------------------------------------


def test_no_budget_says_so_rather_than_showing_zeros(session, user):
    result = budget_progress(session, user.id, month=MONTH, today=TODAY)
    assert result["available"] is False
    assert result["budgets"] == []


def test_spending_is_measured_against_the_limit(session, user):
    spend(session, user, "6240", "food")
    set_budget(session, user.id, "food", "8000")

    item = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]
    assert item["spent"] == Decimal("6240.00")
    assert item["remaining"] == Decimal("1760.00")
    assert item["share"] == 78
    assert item["state"] == "ok"


def test_the_spending_figure_matches_the_dashboard_exactly(session, user):
    """If these two ever disagreed about food, both would be worthless."""
    spend(session, user, "2000", "food")
    spend(session, user, "1500", "food")
    set_budget(session, user.id, "food", "8000")

    summary = aggregations.summary(session, MONTH, user_id=user.id)
    from_dashboard = next(
        row["total"] for row in summary["by_category"] if row["category"] == "food"
    )
    from_budget = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]["spent"]

    assert from_budget == from_dashboard


def test_going_over_reports_the_overspend_not_a_negative_remainder(session, user):
    """'You have -₹900 left' is arithmetic, not English."""
    spend(session, user, "5900", "transport")
    set_budget(session, user.id, "transport", "5000")

    item = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]
    assert item["state"] == "over"
    assert item["remaining"] == Decimal("0.00")
    assert item["over_by"] == Decimal("900.00")
    assert item["share"] == 118


def test_a_budget_nearing_its_limit_is_marked(session, user):
    spend(session, user, "8500", "shopping")
    set_budget(session, user.id, "shopping", "10000")
    item = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]
    assert item["state"] == "near"


def test_a_category_with_no_spending_shows_the_whole_limit_left(session, user):
    set_budget(session, user.id, "education", "3000")
    item = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]
    assert item["spent"] == Decimal("0.00")
    assert item["remaining"] == Decimal("3000.00")
    assert item["share"] == 0


def test_only_the_asked_for_month_counts(session, user):
    spend(session, user, "4000", "food", day=5)
    session.add(Transaction(
        user_id=user.id, date=dt.date(2026, 7, 5), description="LAST MONTH",
        normalized_description="last month", amount=Decimal("9000.00"),
        direction="debit", category="food", fingerprint="july-1",
    ))
    session.commit()
    set_budget(session, user.id, "food", "8000")

    item = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"][0]
    assert item["spent"] == Decimal("4000.00")


def test_the_closest_to_its_limit_is_listed_first(session, user):
    spend(session, user, "500", "food")
    spend(session, user, "4800", "transport")
    set_budget(session, user.id, "food", "8000")        # 6%
    set_budget(session, user.id, "transport", "5000")   # 96%

    items = budget_progress(session, user.id, month=MONTH, today=TODAY)["budgets"]
    assert items[0]["category"] == "transport"


def test_the_totals_add_up(session, user):
    spend(session, user, "6000", "food")
    spend(session, user, "2000", "transport")
    set_budget(session, user.id, "food", "8000")
    set_budget(session, user.id, "transport", "5000")

    result = budget_progress(session, user.id, month=MONTH, today=TODAY)
    assert result["total_limit"] == Decimal("13000.00")
    assert result["total_spent"] == Decimal("8000.00")
    assert result["total_remaining"] == Decimal("5000.00")
    assert result["over_count"] == 0


def test_days_left_is_zero_for_a_finished_month(session, user):
    set_budget(session, user.id, "food", "8000")

    current = budget_progress(session, user.id, month=MONTH, today=TODAY)
    assert current["days_left"] == 14      # 31 - 17

    past = budget_progress(session, user.id, month="2026-07", today=TODAY)
    assert past["days_left"] == 0


def test_a_malformed_month_is_refused(session, user):
    set_budget(session, user.id, "food", "8000")
    with pytest.raises(BudgetError, match="YYYY-MM"):
        budget_progress(session, user.id, month="August", today=TODAY)
