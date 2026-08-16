"""Tests for anomaly detection against the database (Phase 6).

The threshold arithmetic is tested in test_core.py. What is tested here is
the seam: that stored rows reach the detector in the shape it expects, that
Decimal amounts survive the trip, and that the flag really does move when
the surrounding history changes.
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s03_db import Base
from app.core.s04_models import Transaction
from app.store.s14_anomaly_service import find_anomalies

TODAY = dt.date(2026, 6, 1)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def add(session, day, amount, category="food", direction="debit"):
    session.add(
        Transaction(
            date=dt.date(2026, 5, day),
            description=f"MERCHANT {day} {amount}",
            normalized_description=f"merchant {day}",
            amount=amount,
            direction=direction,
            category=category,
            category_source="rule",
            fingerprint=f"fp-{category}-{day}-{amount}-{direction}",
        )
    )


def seed_ordinary_history(session, category="food", count=10, amount="400.00"):
    """Enough small, similar transactions to establish a baseline."""
    for day in range(1, count + 1):
        add(session, day, amount, category)


def test_a_huge_charge_is_flagged(session):
    seed_ordinary_history(session)
    add(session, 20, "9400.00")
    session.commit()

    flagged = find_anomalies(session, today=TODAY)

    assert len(flagged) == 1
    assert flagged[0]["amount"] == "9400.00"


def test_the_reason_reads_like_a_sentence(session):
    seed_ordinary_history(session)
    add(session, 20, "9400.00")
    session.commit()

    reason = find_anomalies(session, today=TODAY)[0]["reason"]

    assert "9,400.00" in reason      # Indian digit grouping
    assert "food" in reason
    assert "x your usual" in reason


def test_ordinary_spending_is_not_flagged(session):
    seed_ordinary_history(session)
    session.commit()

    assert find_anomalies(session, today=TODAY) == []


def test_too_little_history_means_no_flag(session):
    """Below 8 prior transactions the average means nothing, so no call."""
    seed_ordinary_history(session, count=4)
    add(session, 20, "9400.00")
    session.commit()

    assert find_anomalies(session, today=TODAY) == []


def test_credits_are_never_anomalies(session):
    """A large salary is not unusual spending."""
    seed_ordinary_history(session, category="income")
    add(session, 20, "500000.00", category="income", direction="credit")
    session.commit()

    flagged = find_anomalies(session, today=TODAY)

    assert all(row["direction"] == "debit" for row in flagged)


def test_each_category_has_its_own_baseline(session):
    """Rent being large is normal; food being rent-sized is not."""
    seed_ordinary_history(session, category="rent", amount="12000.00")
    seed_ordinary_history(session, category="food", amount="400.00")
    add(session, 20, "12000.00", category="food")
    session.commit()

    flagged = find_anomalies(session, today=TODAY)

    assert len(flagged) == 1
    assert flagged[0]["category"] == "food"


def test_a_flag_disappears_once_the_spending_is_normal(session):
    """Why this is computed per request and never stored in a column."""
    seed_ordinary_history(session)
    add(session, 20, "9400.00")
    session.commit()
    assert len(find_anomalies(session, today=TODAY)) == 1

    # The same amount, over and over, is no longer extraordinary.
    for day in range(21, 29):
        add(session, day, "9400.00")
    session.commit()

    assert find_anomalies(session, today=TODAY) == []


def test_flagged_rows_carry_their_database_id(session):
    """The UI needs the id to link a flag back to its transaction."""
    seed_ordinary_history(session)
    add(session, 20, "9400.00")
    session.commit()

    assert isinstance(find_anomalies(session, today=TODAY)[0]["id"], int)


def test_empty_database_has_no_anomalies(session):
    assert find_anomalies(session, today=TODAY) == []
