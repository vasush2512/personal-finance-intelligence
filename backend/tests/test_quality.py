"""Data quality checks (Phase 4).

The thing most worth pinning here is that a check reports and does not repair.
A dashboard that quietly rewrites rows to make itself look healthier is worse
than no dashboard.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s01_constants import SOURCE_NONE, SOURCE_RULE
from app.core.s03_db import Base
from app.core.s04_models import Transaction, Upload
from app.store.s12c_quality import apply_fix, data_quality

TODAY = dt.date(2026, 8, 15)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def add(session, date, category, source=SOURCE_RULE, direction="debit",
        amount="450.00", upload_id=None, counter=[0]):
    counter[0] += 1
    session.add(
        Transaction(
            date=date,
            description=f"MERCHANT {counter[0]}",
            normalized_description=f"merchant {counter[0]}",
            amount=Decimal(amount),
            direction=direction,
            category=category,
            category_source=source,
            fingerprint=f"fp-{counter[0]}",
            upload_id=upload_id,
        )
    )
    session.commit()


def issue(session, key, today=TODAY):
    report = data_quality(session, today=today)
    return next(entry for entry in report["issues"] if entry["key"] == key)


# --- the report shape ------------------------------------------------------


def test_clean_checks_are_still_reported(session):
    """Zero is a result. Hiding it loses the difference from 'never ran'."""
    add(session, dt.date(2026, 6, 1), "food")
    report = data_quality(session, today=TODAY)

    assert report["checks_run"] == len(report["issues"])
    assert report["issues_found"] == 0
    assert all(entry["count"] == 0 for entry in report["issues"])


def test_worse_problems_come_first(session):
    upload = Upload(filename="all-debits.csv")
    session.add(upload)
    session.commit()
    for day in range(1, 25):
        add(session, dt.date(2026, 6, day), "other", upload_id=upload.id)

    severities = [entry["severity"] for entry in data_quality(session, today=TODAY)["issues"]]
    assert severities == sorted(severities, key={"high": 0, "medium": 1, "low": 2}.get)


# --- individual checks -----------------------------------------------------


def test_a_file_with_only_debits_is_flagged(session):
    upload = Upload(filename="statement.csv")
    session.add(upload)
    session.commit()
    for day in range(1, 25):
        add(session, dt.date(2026, 6, day), "food", upload_id=upload.id)

    found = issue(session, "single_direction")
    assert found["count"] == 1
    assert found["severity"] == "high"
    assert "statement.csv" in found["detail"]


def test_a_short_all_debit_file_is_not_flagged(session):
    """Five debits in a row is a normal week, not a broken import."""
    upload = Upload(filename="short.csv")
    session.add(upload)
    session.commit()
    for day in range(1, 6):
        add(session, dt.date(2026, 6, day), "food", upload_id=upload.id)

    assert issue(session, "single_direction")["count"] == 0


def test_a_file_with_both_directions_is_not_flagged(session):
    upload = Upload(filename="normal.csv")
    session.add(upload)
    session.commit()
    for day in range(1, 25):
        direction = "credit" if day == 1 else "debit"
        add(session, dt.date(2026, 6, day), "food", direction=direction,
            upload_id=upload.id)

    assert issue(session, "single_direction")["count"] == 0


def test_future_dates_are_flagged(session):
    add(session, dt.date(2026, 6, 1), "food")
    add(session, dt.date(2027, 1, 1), "food")
    assert issue(session, "future_dated")["count"] == 1


def test_a_missing_month_is_a_gap_but_consecutive_months_are_not(session):
    add(session, dt.date(2026, 1, 5), "food")
    add(session, dt.date(2026, 2, 5), "food")
    assert issue(session, "month_gaps")["count"] == 0

    add(session, dt.date(2026, 6, 5), "food")
    found = issue(session, "month_gaps")
    assert found["count"] == 1
    assert "2026-02" in found["detail"]


def test_the_uncategorized_share_drives_the_severity(session):
    for _ in range(9):
        add(session, dt.date(2026, 6, 1), "other")
    add(session, dt.date(2026, 6, 1), "food")

    found = issue(session, "uncategorized")
    assert found["count"] == 9
    assert found["severity"] == "high"  # 90%


def test_zero_amounts_are_flagged(session):
    add(session, dt.date(2026, 6, 1), "food", amount="0.00")
    assert issue(session, "zero_amount")["count"] == 1


def test_skipped_rows_are_reported_from_the_upload_record(session):
    session.add(Upload(filename="messy.csv", rows_parsed=100, rows_skipped=7))
    session.commit()
    found = issue(session, "skipped_rows")
    assert found["count"] == 7
    assert "messy.csv" in found["detail"]


# --- the one automatic repair ----------------------------------------------


def test_reading_the_report_never_changes_anything(session):
    add(session, dt.date(2026, 6, 1), "other", source=SOURCE_RULE)

    data_quality(session, today=TODAY)
    data_quality(session, today=TODAY)

    row = session.query(Transaction).one()
    assert row.category_source == SOURCE_RULE  # untouched by reading


def test_the_fix_relabels_only_the_rows_that_are_provably_wrong(session):
    add(session, dt.date(2026, 6, 1), "other", source=SOURCE_RULE)   # wrong
    add(session, dt.date(2026, 6, 2), "food", source=SOURCE_RULE)    # genuine

    assert apply_fix(session, "stale_rule_source") == 1

    rows = {row.category: row.category_source
            for row in session.query(Transaction).all()}
    assert rows["other"] == SOURCE_NONE
    assert rows["food"] == SOURCE_RULE


def test_the_fix_changes_nothing_but_the_label(session):
    add(session, dt.date(2026, 6, 1), "other", source=SOURCE_RULE, amount="450.00")
    apply_fix(session, "stale_rule_source")

    row = session.query(Transaction).one()
    assert row.category == "other"
    assert row.amount == Decimal("450.00")
    assert row.date == dt.date(2026, 6, 1)


def test_running_the_fix_twice_is_harmless(session):
    add(session, dt.date(2026, 6, 1), "other", source=SOURCE_RULE)
    assert apply_fix(session, "stale_rule_source") == 1
    assert apply_fix(session, "stale_rule_source") == 0


def test_no_other_issue_can_be_fixed_automatically(session):
    """Every other problem needs a person or a corrected file."""
    for key in ("uncategorized", "single_direction", "future_dated", "month_gaps"):
        with pytest.raises(KeyError):
            apply_fix(session, key)
