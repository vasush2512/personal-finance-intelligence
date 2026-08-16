"""Tests for the classifier wiring (Phase 4).

The model itself — the vectorizers, the threshold, the split — is trainer.py's
business and is covered in test_core.py. What is tested here is the seam
between the database and the trainer: that retrain reads the right rows, that
it refuses to train on too little data, that an import applies the model only
where the rules gave up, and that a user's correction survives all of it.
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.s01_constants import SOURCE_NONE, UNCATEGORIZED
from app.core.s03_db import Base
from app.pipeline.s09_model import MIN_TRAINING_ROWS, NotEnoughData
from app.core.s04_models import Transaction
from app.store import s11_importer as importer
from app.store.s11_importer import categorize, import_statement
from app.store.s13_model_service import retrain

# Merchants with enough repetition per category for a stratified split.
TRAINING_MERCHANTS = {
    "food": ["swiggy order", "zomato dinner", "dominos pizza", "kfc bucket",
             "cafe coffee day", "biryani house", "subway sandwich"],
    "groceries": ["blinkit delivery", "zepto order", "bigbasket weekly",
                  "dmart shopping", "reliance fresh", "kirana store", "amul milk"],
    "transport": ["uber ride", "ola cab", "rapido bike", "irctc booking",
                  "petrol hpcl", "fastag recharge", "metro dmrc"],
    "shopping": ["amazon order", "flipkart order", "myntra fashion", "ajio style",
                 "meesho order", "nykaa beauty", "decathlon sports"],
    "bills_utilities": ["jio recharge", "airtel bill", "electricity bescom",
                        "broadband act fibernet", "gas indane", "water bill",
                        "insurance premium"],
    "health": ["apollo pharmacy", "pharmeasy order", "1mg medicines",
               "netmeds order", "medplus chemist", "hospital clinic", "gym fitness"],
    "education": ["byjus course", "unacademy class", "coursera course",
                  "udemy course", "upgrad program", "college fee", "tuition fee"],
    "entertainment": ["netflix subscription", "spotify premium", "hotstar plan",
                      "bookmyshow tickets", "pvr cinema", "inox movie",
                      "steam games"],
}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


# Each merchant appears with several narration endings, the way a real
# statement repeats a merchant with different suffixes. Below roughly 200
# rows the model is so unsure that the 0.55 threshold makes it abstain on
# everything, and these tests would be measuring nothing.
NARRATION_SUFFIXES = ["", " payment", " order", " bangalore"]


def seed_labelled_rows(session, source="rule"):
    """Write enough rule-labelled rows that training is allowed."""
    counter = 0
    for category, descriptions in TRAINING_MERCHANTS.items():
        for description in descriptions:
            for suffix in NARRATION_SUFFIXES:
                counter += 1
                session.add(
                    Transaction(
                        date=dt.date(2026, 5, 1),
                        description=(description + suffix).upper(),
                        normalized_description=description + suffix,
                        amount="100.00",
                        direction="debit",
                        category=category,
                        category_source=source,
                        fingerprint=f"seed-{counter}",
                    )
                )
    session.commit()
    return counter


# --- retrain --------------------------------------------------------------

def test_retrain_refuses_when_there_is_too_little_data(session, tmp_path):
    session.add(
        Transaction(
            date=dt.date(2026, 5, 1), description="SWIGGY",
            normalized_description="swiggy",
            amount="100.00", direction="debit", category="food",
            category_source="rule", fingerprint="only-one",
        )
    )
    session.commit()

    with pytest.raises(NotEnoughData) as error:
        retrain(session, model_path=tmp_path / "model.joblib")

    assert str(MIN_TRAINING_ROWS) in str(error.value)


def test_retrain_reports_accuracy_and_row_count(session, tmp_path):
    seeded = seed_labelled_rows(session)
    model_path = tmp_path / "model.joblib"

    report = retrain(session, model_path=model_path)

    assert report["trained"] is True
    assert report["labelled_rows"] == seeded
    assert 0.0 <= report["holdout_accuracy"] <= 1.0
    assert model_path.exists()


def test_uncategorized_rows_are_not_used_as_training_labels(session, tmp_path):
    seed_labelled_rows(session)
    session.add(
        Transaction(
            date=dt.date(2026, 5, 2), description="MYSTERY",
            normalized_description="mystery",
            amount="50.00", direction="debit", category=UNCATEGORIZED,
            category_source="rule", fingerprint="mystery-1",
        )
    )
    session.commit()

    report = retrain(session, model_path=tmp_path / "model.joblib")

    assert UNCATEGORIZED not in report["classes"]


def test_user_corrections_are_training_data(session, tmp_path):
    seed_labelled_rows(session, source="user")

    report = retrain(session, model_path=tmp_path / "model.joblib")

    assert report["trained"] is True


# --- the model at import time ---------------------------------------------

def test_model_labels_what_the_rules_missed(session, tmp_path):
    """A merchant no rule names should still get a category from the model.

    'zomatoo' is a misspelling, so the \\bzomato\\b rule does not fire. The
    character n-grams still see 'zomat' and place it as food. This is the
    exact case char_wb features exist for.
    """
    seed_labelled_rows(session)
    model_path = tmp_path / "model.joblib"
    retrain(session, model_path=model_path)

    rows = [
        {
            "normalized_description": "zomatoo dinner",
            "date": "2026-06-01", "amount": "250.00", "direction": "debit",
        }
    ]
    categorize(rows, model_path=model_path)

    assert rows[0]["category"] != UNCATEGORIZED
    assert rows[0]["category_source"] == "model"
    assert rows[0]["confidence"] is not None


def test_rules_win_over_the_model(session, tmp_path):
    seed_labelled_rows(session)
    model_path = tmp_path / "model.joblib"
    retrain(session, model_path=model_path)

    rows = [{"normalized_description": "swiggy order", "date": "2026-06-01",
             "amount": "250.00", "direction": "debit"}]
    categorize(rows, model_path=model_path)

    # A keyword rule matches 'swiggy', so the model never gets a say.
    assert rows[0]["category"] == "food"
    assert rows[0]["category_source"] == "rule"


def test_categorizing_works_with_no_model_file(tmp_path):
    """Before the first retrain there is no model. Importing must still work."""
    rows = [{"normalized_description": "totally unknown merchant",
             "date": "2026-06-01", "amount": "10.00", "direction": "debit"}]

    filled = categorize(rows, model_path=tmp_path / "does-not-exist.joblib")

    assert filled == 0
    assert rows[0]["category"] == UNCATEGORIZED
    # No rule matched and there is no model, so nothing labelled this row.
    assert rows[0]["category_source"] == SOURCE_NONE


def test_a_user_label_is_never_overwritten(session, tmp_path):
    seed_labelled_rows(session)
    model_path = tmp_path / "model.joblib"
    retrain(session, model_path=model_path)

    rows = [
        {
            "normalized_description": "swiggy order",
            "category": "shopping",
            "category_source": "user",
            "confidence": None,
            "date": "2026-06-01", "amount": "250.00", "direction": "debit",
        }
    ]
    categorize(rows, model_path=model_path)

    assert rows[0]["category_source"] == "user"


def test_full_import_applies_the_model(session, tmp_path, monkeypatch):
    """End to end: seed, train, then import a statement through the service."""
    seed_labelled_rows(session)
    model_path = tmp_path / "model.joblib"
    retrain(session, model_path=model_path)
    monkeypatch.setattr(importer, "MODEL_PATH", model_path)

    csv_bytes = (
        b"Date,Narration,Withdrawal Amt.,Deposit Amt.\n"
        b"01/06/2026,UPI/DR/9/BIGBASKET DAILY BASKET/HDFC/bb@ybl,780.00,\n"
    )
    import_statement(session, "june.csv", csv_bytes)

    imported = session.execute(
        select(Transaction).where(Transaction.description.ilike("%BIGBASKET DAILY%"))
    ).scalar_one()
    assert imported.category == "groceries"
