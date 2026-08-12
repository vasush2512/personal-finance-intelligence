"""Tests for the database side of importing a statement.

The parser itself is covered in test_core.py. These tests cover what happens
between "parsed rows" and "rows in the database": deduplication against the
existing table, deduplication inside one file, and the counts we report back.

Each test gets its own in-memory database, so nothing here touches
data/expenses.db.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Transaction, Upload
from app.services.importer import import_statement

# --- three different bank CSV shapes --------------------------------------

TWO_COLUMN_CSV = b"""Statement of Account
Account Number: XXXXXX1234

Date,Narration,Withdrawal Amt.,Deposit Amt.
05/05/2026,UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl,409.50,
06/05/2026,NEFT-AXIS-SALARY MAY,,"1,20,000.00"
07/05/2026,POS 4512XXXXXXXX1234 BLINKIT MUMBAI,"1,051.00",
*** End of Statement ***
"""

SIGNED_AMOUNT_CSV = b"""Transaction Date,Particulars,Amount
2026-05-05,UPI/DR/999/ZOMATO/ICICI,-320.00
2026-05-06,SALARY CREDIT MAY,120000.00
"""

AMOUNT_PLUS_TYPE_CSV = b"""Value Date|Transaction Remarks|Txn Amount|DR/CR
05-May-2026|IMPS/UBER INDIA|450.00|DR
06-May-2026|INTEREST CREDIT|1200.00|CR
"""


@pytest.fixture
def session():
    """A fresh in-memory database per test."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def count_transactions(session):
    return session.execute(select(func.count(Transaction.id))).scalar_one()


# --- the three shapes all import ------------------------------------------

@pytest.mark.parametrize(
    "csv_bytes,expected_imported",
    [
        (TWO_COLUMN_CSV, 3),
        (SIGNED_AMOUNT_CSV, 2),
        (AMOUNT_PLUS_TYPE_CSV, 2),
    ],
)
def test_imports_every_csv_shape(session, csv_bytes, expected_imported):
    result = import_statement(session, "statement.csv", csv_bytes)

    assert result["imported"] == expected_imported
    assert count_transactions(session) == expected_imported


def test_two_column_layout_sets_direction(session):
    import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    directions = session.execute(
        select(Transaction.direction).order_by(Transaction.date)
    ).scalars().all()
    assert directions == ["debit", "credit", "debit"]


def test_amount_round_trips_as_decimal(session):
    import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    swiggy = session.execute(
        select(Transaction).where(Transaction.description.ilike("%SWIGGY%"))
    ).scalar_one()

    assert swiggy.amount == Decimal("409.50")
    assert isinstance(swiggy.amount, Decimal)


def test_indian_grouped_amount_is_parsed(session):
    import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    salary = session.execute(
        select(Transaction).where(Transaction.direction == "credit")
    ).scalar_one()
    assert salary.amount == Decimal("120000.00")


# --- deduplication --------------------------------------------------------

def test_reuploading_the_same_file_imports_nothing(session):
    first = import_statement(session, "statement.csv", TWO_COLUMN_CSV)
    second = import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    assert first["imported"] == 3
    assert second["imported"] == 0
    assert second["duplicates"] == 3
    assert count_transactions(session) == 3


def test_duplicates_inside_one_file_are_dropped(session):
    doubled = TWO_COLUMN_CSV + b"05/05/2026,UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl,409.50,\n"

    result = import_statement(session, "statement.csv", doubled)

    assert result["duplicates"] == 1
    assert count_transactions(session) == 3


def test_overlapping_statements_only_add_new_rows(session):
    import_statement(session, "may.csv", TWO_COLUMN_CSV)

    overlapping = b"""Date,Narration,Withdrawal Amt.,Deposit Amt.
07/05/2026,POS 4512XXXXXXXX1234 BLINKIT MUMBAI,"1,051.00",
08/05/2026,UPI/DR/777/UBER INDIA/HDFC,250.00,
"""
    result = import_statement(session, "june.csv", overlapping)

    assert result["imported"] == 1
    assert result["duplicates"] == 1
    assert count_transactions(session) == 4


# --- counts and bookkeeping -----------------------------------------------

def test_junk_rows_are_skipped_not_imported(session):
    result = import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    # The footer line has no date or amount and must not become a transaction.
    assert result["skipped"] >= 1
    assert result["rows_parsed"] == 3


def test_upload_row_records_the_counts(session):
    result = import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    upload = session.get(Upload, result["upload_id"])
    assert upload.filename == "statement.csv"
    assert upload.rows_imported == 3
    assert upload.duplicates == 0


def test_transactions_are_linked_to_their_upload(session):
    result = import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    upload_ids = session.execute(select(Transaction.upload_id)).scalars().all()
    assert set(upload_ids) == {result["upload_id"]}


def test_rows_are_categorized_on_the_way_in(session):
    """Phase 3: the keyword rules run during import, not on a later pass."""
    import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    categories = session.execute(select(Transaction.category)).scalars().all()
    assert set(categories) == {"food", "income", "groceries"}


def test_deleting_an_upload_removes_its_transactions(session):
    result = import_statement(session, "statement.csv", TWO_COLUMN_CSV)

    session.delete(session.get(Upload, result["upload_id"]))
    session.commit()

    assert count_transactions(session) == 0
