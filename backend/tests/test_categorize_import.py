"""Tests for categorization at import time (Phase 3).

The rule matcher and the normalizer are tested in isolation in test_core.py.
What is tested here is the wiring: a row that goes through import_statement
should come out of the database with a real category on it.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.s01_constants import (
    CATEGORIES,
    SOURCE_NONE,
    SOURCE_RULE,
    UNCATEGORIZED,
)
from app.core.s03_db import Base
from app.core.s04_models import Transaction
from app.store.s11_importer import import_statement

MIXED_CSV = b"""Date,Narration,Withdrawal Amt.,Deposit Amt.
05/05/2026,UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl/Order,409.50,
06/05/2026,NEFT-AXISCN0123456789-SALARY MAY,,"1,20,000.00"
07/05/2026,UPI/DR/207855788629/HOUSE RENT MARCH/SBI/landlord@oksbi,11722.00,
08/05/2026,UPI/DR/372511167022/UDEMY ONLINE/HDFC/udemy@ybl/Course,2611.00,
09/05/2026,POS 4512XXXXXXXX1234 BLINKIT MUMBAI,1051.00,
10/05/2026,UPI/DR/555/QWERTY ENTERPRISES/HDFC/qwerty@ybl,300.00,
"""


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def categories_by_description(session):
    """{description: category} for everything in the database."""
    rows = session.execute(select(Transaction)).scalars().all()
    return {row.description: row.category for row in rows}


def test_known_merchants_get_real_categories(session):
    import_statement(session, "statement.csv", MIXED_CSV)
    found = categories_by_description(session)

    assert found["UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl/Order"] == "food"
    assert found["NEFT-AXISCN0123456789-SALARY MAY"] == "income"
    assert found["UPI/DR/207855788629/HOUSE RENT MARCH/SBI/landlord@oksbi"] == "rent"
    assert found["UPI/DR/372511167022/UDEMY ONLINE/HDFC/udemy@ybl/Course"] == "education"
    assert found["POS 4512XXXXXXXX1234 BLINKIT MUMBAI"] == "groceries"


def test_unknown_merchant_stays_uncategorized(session):
    import_statement(session, "statement.csv", MIXED_CSV)
    found = categories_by_description(session)

    # No rule mentions this merchant. Phase 4's model is what will guess it.
    assert found["UPI/DR/555/QWERTY ENTERPRISES/HDFC/qwerty@ybl"] == UNCATEGORIZED


def test_every_stored_category_is_a_known_one(session):
    import_statement(session, "statement.csv", MIXED_CSV)

    stored = session.execute(select(Transaction.category)).scalars().all()
    assert set(stored) <= set(CATEGORIES)


def test_only_matched_rows_are_marked_as_rule(session):
    """A rule label means a rule matched — not merely that the rules ran.

    MIXED_CSV contains a merchant no keyword covers, so the import must produce
    both labels. Marking every row 'rule' is what made rule coverage look like
    100% when it was not.
    """
    import_statement(session, "statement.csv", MIXED_CSV)

    sources = session.execute(select(Transaction.category_source)).scalars().all()
    assert set(sources) == {SOURCE_RULE, SOURCE_NONE}


def test_unmatched_rows_are_the_uncategorized_ones(session):
    """'none' and 'other' must agree — they describe the same rows."""
    import_statement(session, "statement.csv", MIXED_CSV)

    rows = session.execute(
        select(Transaction.category, Transaction.category_source)
    ).all()

    for category, source in rows:
        if source == SOURCE_NONE:
            assert category == UNCATEGORIZED
        if category == UNCATEGORIZED:
            assert source == SOURCE_NONE


def test_rules_leave_confidence_empty(session):
    """Confidence is a model probability. A rule has no probability."""
    import_statement(session, "statement.csv", MIXED_CSV)

    confidences = session.execute(select(Transaction.confidence)).scalars().all()
    assert all(value is None for value in confidences)


def test_income_wins_over_transfer_wording(session):
    """'SALARY' must beat the generic transfer keywords in NEFT narrations."""
    import_statement(session, "statement.csv", MIXED_CSV)
    found = categories_by_description(session)

    assert found["NEFT-AXISCN0123456789-SALARY MAY"] == "income"


def test_reimporting_does_not_change_existing_categories(session):
    """A duplicate row is skipped entirely, so nothing is re-labelled."""
    import_statement(session, "statement.csv", MIXED_CSV)

    swiggy = session.execute(
        select(Transaction).where(Transaction.description.ilike("%SWIGGY%"))
    ).scalar_one()
    swiggy.category = "shopping"
    swiggy.category_source = "user"
    session.commit()

    import_statement(session, "statement.csv", MIXED_CSV)

    session.refresh(swiggy)
    assert swiggy.category == "shopping"
    assert swiggy.category_source == "user"
