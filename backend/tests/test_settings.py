"""Per-user settings, and the one that changes behaviour.

Anomaly sensitivity is the only setting here that does anything other than
change how a figure is written down. These tests are mostly about proving it
actually moves the detector, rather than being a dropdown that stores a word.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s03_db import Base
from app.core.s04_models import Transaction, User, UserSettings
from app.pipeline.s10_anomalies import SENSITIVITY, detect_anomalies, sigma_for
from app.store.s14_anomaly_service import find_anomalies
from app.store.s15c_settings import (
    SettingsError,
    get_settings,
    sensitivity_for,
    update_settings,
)

TODAY = dt.date(2026, 8, 17)


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


def history(session, user, amounts, category="food"):
    """A run of ordinary spending, then whatever is passed last."""
    for index, amount in enumerate(amounts):
        session.add(Transaction(
            user_id=user.id,
            date=TODAY - dt.timedelta(days=len(amounts) - index),
            description=f"SHOP {index}",
            normalized_description=f"shop {index}",
            amount=Decimal(str(amount)),
            direction="debit",
            category=category,
            fingerprint=f"fp-{category}-{index}",
        ))
    session.commit()


# --- defaults --------------------------------------------------------------


def test_settings_are_created_on_first_read_with_defaults(session, user):
    """An account that never opens Settings behaves exactly as before."""
    assert session.query(UserSettings).count() == 0

    settings = get_settings(session, user.id)
    assert settings.anomaly_sensitivity == "medium"
    assert settings.currency == "INR"
    assert settings.date_format == "dmy"
    assert session.query(UserSettings).count() == 1


def test_reading_twice_does_not_make_two_rows(session, user):
    get_settings(session, user.id)
    get_settings(session, user.id)
    assert session.query(UserSettings).count() == 1


def test_medium_is_the_documented_default_threshold():
    assert sigma_for("medium") == 2.5
    assert sigma_for(None) == 2.5
    # An unrecognised value falls back rather than crashing a detector.
    assert sigma_for("nonsense") == 2.5


def test_lower_sensitivity_means_a_higher_bar():
    assert SENSITIVITY["low"] > SENSITIVITY["medium"] > SENSITIVITY["high"]


# --- updating --------------------------------------------------------------


def test_a_setting_can_be_changed(session, user):
    update_settings(session, user.id, anomaly_sensitivity="high")
    assert sensitivity_for(session, user.id) == "high"


def test_an_unknown_value_is_refused_rather_than_coerced(session, user):
    for field, bad in [
        ("anomaly_sensitivity", "extreme"),
        ("currency", "MOON"),
        ("date_format", "roman"),
        ("default_period", "fortnight"),
    ]:
        with pytest.raises(SettingsError, match="Unknown"):
            update_settings(session, user.id, **{field: bad})

    # Nothing was written by the failed attempts.
    settings = get_settings(session, user.id)
    assert settings.anomaly_sensitivity == "medium"
    assert settings.currency == "INR"


def test_changing_one_setting_leaves_the_others_alone(session, user):
    update_settings(session, user.id, currency="USD")
    settings = get_settings(session, user.id)
    assert settings.currency == "USD"
    assert settings.anomaly_sensitivity == "medium"


def test_settings_belong_to_one_user(session, user):
    other = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(other)
    session.commit()

    update_settings(session, user.id, anomaly_sensitivity="high")
    assert sensitivity_for(session, other.id) == "medium"


# --- it actually moves the detector ----------------------------------------


def test_sensitivity_changes_what_gets_flagged(session, user):
    """The point of the setting. A dropdown that only stores a word would
    pass every test above and none of this one."""
    # Steady spending around 400 (sigma 7.5), then a charge at 421 — which
    # sits between the 3.0 threshold (422.5) and the 2.0 one (415). A charge
    # far outside every threshold would be flagged at all three and would
    # prove nothing about the setting.
    history(session, user, [400, 410, 390, 405, 395, 400, 410, 390, 421])

    rows = lambda level: len(  # noqa: E731
        find_anomalies(session, today=TODAY, sensitivity=level, user_id=user.id)
    )

    high = rows("high")
    medium = rows("medium")
    low = rows("low")

    # More sensitive never flags fewer.
    assert high >= medium >= low
    # And the setting is doing something rather than storing a word: this
    # charge is worth reviewing at 2.0 sigma and not at 3.0.
    assert (high, medium, low) == (1, 1, 0)


def test_the_default_matches_the_old_hardcoded_behaviour(session, user):
    """This existed before the setting did, and must not have changed."""
    history(session, user, [400, 410, 390, 405, 395, 400, 410, 390, 2000])

    rows = [dict(row) for row in
            find_anomalies(session, today=TODAY, user_id=user.id)]
    with_medium = [dict(row) for row in
                   find_anomalies(session, today=TODAY, sensitivity="medium",
                                  user_id=user.id)]

    assert rows == with_medium


def test_the_detector_takes_the_setting_without_a_database(session, user):
    """detect_anomalies stays pure — the sensitivity is passed in, not looked up."""
    plain = [
        {"id": index, "date": (TODAY - dt.timedelta(days=20 - index)).isoformat(),
         "description": "SHOP", "amount": amount, "direction": "debit",
         "category": "food"}
        for index, amount in enumerate([400, 410, 390, 405, 395, 400, 410, 390, 421])
    ]

    high = detect_anomalies(plain, today=TODAY, sensitivity="high")
    low = detect_anomalies(plain, today=TODAY, sensitivity="low")
    assert len(high) == 1 and len(low) == 0
