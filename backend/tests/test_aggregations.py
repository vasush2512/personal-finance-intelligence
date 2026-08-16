"""Tests for the dashboard arithmetic (Phase 5a).

The rule that matters most here: a transfer is not spending. Every total in
the app depends on that, and getting it wrong inflates the numbers in a way
that looks plausible.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s03_db import Base
from app.core.s04_models import Transaction, Upload
from app.store import s12_aggregations as aggregations


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def add(session, date, description, amount, direction, category, counter=[0]):
    counter[0] += 1
    session.add(
        Transaction(
            date=date,
            description=description.upper(),
            normalized_description=description,
            amount=amount,
            direction=direction,
            category=category,
            category_source="rule",
            fingerprint=f"fp-{counter[0]}-{description}-{date}",
        )
    )


@pytest.fixture
def populated(session):
    add(session, dt.date(2026, 5, 3), "swiggy order", "400.00", "debit", "food")
    add(session, dt.date(2026, 5, 10), "blinkit groceries", "1000.00", "debit", "groceries")
    add(session, dt.date(2026, 5, 20), "swiggy dinner", "600.00", "debit", "food")
    add(session, dt.date(2026, 5, 1), "techcadd salary", "50000.00", "credit", "income")
    # A transfer in each direction. Neither is spending or income.
    add(session, dt.date(2026, 5, 15), "self transfer", "5000.00", "debit", "transfer")
    add(session, dt.date(2026, 5, 16), "own account", "5000.00", "credit", "transfer")
    add(session, dt.date(2026, 6, 4), "uber ride", "250.00", "debit", "transport")
    session.commit()
    return session


# --- totals ---------------------------------------------------------------

def test_transfers_are_not_spending(populated):
    """400 + 1000 + 600 + 250 = 2250. The 5000 transfer must not appear."""
    assert aggregations.total_spent(populated) == Decimal("2250.00")


def test_transfers_are_not_income(populated):
    assert aggregations.total_income(populated) == Decimal("50000.00")


def test_net_is_income_minus_spending(populated):
    result = aggregations.summary(populated)
    assert result["net"] == Decimal("47750.00")


def test_totals_are_decimals_not_floats(populated):
    result = aggregations.summary(populated)
    assert isinstance(result["total_spent"], Decimal)
    assert isinstance(result["net"], Decimal)


def test_empty_database_totals_zero_not_none(session):
    result = aggregations.summary(session)
    assert result["total_spent"] == Decimal("0.00")
    assert result["net"] == Decimal("0.00")
    assert result["by_category"] == []


def test_transaction_count_includes_transfers(populated):
    """The count is 'how many rows', not 'how many count as spending'."""
    assert aggregations.transaction_count(populated) == 7


# --- month filtering ------------------------------------------------------

def test_month_filter_limits_the_totals(populated):
    assert aggregations.total_spent(populated, "2026-06") == Decimal("250.00")
    assert aggregations.total_spent(populated, "2026-05") == Decimal("2000.00")


def test_december_rolls_into_the_next_year(session):
    add(session, dt.date(2026, 12, 25), "amazon order", "100.00", "debit", "shopping")
    add(session, dt.date(2027, 1, 2), "amazon order", "700.00", "debit", "shopping")
    session.commit()

    assert aggregations.total_spent(session, "2026-12") == Decimal("100.00")


# --- category and merchant breakdowns -------------------------------------

def test_categories_are_sorted_biggest_first(populated):
    categories = aggregations.totals_by_category(populated)

    assert [row["category"] for row in categories] == ["food", "groceries", "transport"]
    assert categories[0]["total"] == Decimal("1000.00")


def test_transfer_is_absent_from_the_category_split(populated):
    categories = aggregations.totals_by_category(populated)
    assert "transfer" not in [row["category"] for row in categories]


def test_merchants_are_grouped_by_first_word(populated):
    merchants = aggregations.top_merchants(populated)
    by_name = {row["merchant"]: row for row in merchants}

    # 'swiggy order' and 'swiggy dinner' are one merchant.
    assert by_name["swiggy"]["total"] == Decimal("1000.00")
    assert by_name["swiggy"]["count"] == 2


def test_merchant_list_is_capped(populated):
    merchants = aggregations.top_merchants(populated, limit=2)
    assert len(merchants) == 2


def test_merchant_name_of_empty_description():
    assert aggregations.merchant_name("") == "unknown"


# --- trends ---------------------------------------------------------------

def test_trends_are_grouped_by_month_oldest_first(populated):
    trends = aggregations.monthly_trends(populated)

    assert [point["month"] for point in trends] == ["2026-05", "2026-06"]
    assert trends[0]["spent"] == Decimal("2000.00")
    assert trends[0]["income"] == Decimal("50000.00")
    assert trends[1]["spent"] == Decimal("250.00")


def test_trends_exclude_transfers(populated):
    trends = aggregations.monthly_trends(populated)
    may = trends[0]
    assert may["spent"] == Decimal("2000.00")   # not 7000
    assert may["income"] == Decimal("50000.00")  # not 55000


def test_trends_on_an_empty_database(session):
    assert aggregations.monthly_trends(session) == []


# --- deleting an upload ---------------------------------------------------

def test_deleting_an_upload_changes_the_totals(session):
    upload = Upload(filename="may.csv", rows_parsed=1, rows_imported=1)
    session.add(upload)
    session.flush()
    session.add(
        Transaction(
            upload_id=upload.id, date=dt.date(2026, 5, 3), description="SWIGGY",
            normalized_description="swiggy", amount="400.00", direction="debit",
            category="food", category_source="rule", fingerprint="delete-me",
        )
    )
    session.commit()
    assert aggregations.total_spent(session) == Decimal("400.00")

    session.delete(upload)
    session.commit()

    assert aggregations.total_spent(session) == Decimal("0.00")
