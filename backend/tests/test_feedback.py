"""Category corrections and what the Model page reports (Phase 3).

The point of storing a correction is to be able to tell "the classifier was
confidently wrong" apart from "no rule matched and a person filled it in".
These tests are mostly about keeping that distinction intact.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s01_constants import SOURCE_MODEL, SOURCE_NONE, SOURCE_RULE, SOURCE_USER
from app.core.s03_db import Base
from app.core.s04_models import CategoryFeedback, Transaction
from app.store.s13a_model_stats import model_stats
from app.store.s14c_feedback import recent_corrections, record_correction


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def add(session, description, category, source, confidence=None, counter=[0]):
    counter[0] += 1
    row = Transaction(
        date=dt.date(2026, 6, 1),
        description=description.upper(),
        normalized_description=description,
        amount=Decimal("450.00"),
        direction="debit",
        category=category,
        category_source=source,
        confidence=confidence,
        fingerprint=f"fp-{counter[0]}",
    )
    session.add(row)
    session.commit()
    return row


def correct(session, row, new_category):
    """What the PATCH route does, in the same order."""
    record_correction(session, row, new_category)
    row.category = new_category
    row.category_source = SOURCE_USER
    row.confidence = None
    session.commit()


# --- recording -------------------------------------------------------------


def test_a_correction_remembers_what_the_label_used_to_be(session):
    row = add(session, "swiggy order", "shopping", SOURCE_MODEL, confidence=0.91)
    correct(session, row, "food")

    feedback = session.query(CategoryFeedback).one()
    assert feedback.from_category == "shopping"
    assert feedback.to_category == "food"
    assert feedback.from_source == SOURCE_MODEL
    assert feedback.confidence_before == 0.91


def test_the_transaction_still_ends_up_labelled_by_the_user(session):
    row = add(session, "swiggy order", "shopping", SOURCE_MODEL, confidence=0.91)
    correct(session, row, "food")

    assert row.category_source == SOURCE_USER
    assert row.confidence is None


def test_saving_the_same_category_records_nothing(session):
    """Re-saving an unchanged value must not inflate the correction count."""
    row = add(session, "swiggy order", "food", SOURCE_RULE)
    assert record_correction(session, row, "food") is None
    session.commit()
    assert session.query(CategoryFeedback).count() == 0


def test_correcting_twice_keeps_both_corrections(session):
    """A correction that was itself corrected is a fact, not a mistake."""
    row = add(session, "swiggy order", "shopping", SOURCE_MODEL, confidence=0.8)
    correct(session, row, "groceries")
    correct(session, row, "food")

    history = session.query(CategoryFeedback).order_by(CategoryFeedback.id).all()
    assert [(f.from_category, f.to_category) for f in history] == [
        ("shopping", "groceries"),
        ("groceries", "food"),
    ]
    # The second correction records that a person, not the model, was overruled.
    assert history[1].from_source == SOURCE_USER
    assert history[1].confidence_before is None


def test_the_recent_list_shows_what_was_corrected(session):
    row = add(session, "swiggy order", "shopping", SOURCE_MODEL, confidence=0.7)
    correct(session, row, "food")

    entry = recent_corrections(session)[0]
    assert entry["transaction_id"] == row.id
    assert entry["merchant"]  # derived from the narration, not blank
    assert entry["from_category"] == "shopping"
    assert entry["amount"] == Decimal("450.00")


# --- what the Model page reports -------------------------------------------


def test_every_labeller_appears_even_with_no_rows(session):
    """A missing bar reads as a missing feature, not as a zero."""
    add(session, "swiggy order", "food", SOURCE_RULE)
    sources = {row["source"]: row for row in model_stats(session)["by_source"]}

    assert set(sources) == {SOURCE_RULE, SOURCE_MODEL, SOURCE_USER, SOURCE_NONE}
    assert sources[SOURCE_MODEL]["count"] == 0
    assert sources[SOURCE_RULE]["share"] == 100.0


def test_only_model_labelled_rows_land_in_the_confidence_buckets(session):
    """A rule either matched or did not, and a person is not a probability."""
    add(session, "netflix", "entertainment", SOURCE_MODEL, confidence=0.95)
    add(session, "swiggy", "food", SOURCE_MODEL, confidence=0.80)
    add(session, "rent", "rent", SOURCE_RULE)

    buckets = {b["label"]: b["count"] for b in model_stats(session)["confidence_buckets"]}
    assert buckets["Very high"] == 1
    assert buckets["High"] == 1
    assert sum(buckets.values()) == 2


def test_an_abstention_is_counted_separately_from_a_label(session):
    """Below the threshold the model says nothing. That is it working."""
    add(session, "mystery merchant", "other", SOURCE_NONE, confidence=0.31)
    assert model_stats(session)["abstentions"] == 1


def test_confusions_name_the_pair_the_classifier_got_wrong(session):
    for _ in range(3):
        row = add(session, "swiggy order", "shopping", SOURCE_MODEL, confidence=0.9)
        correct(session, row, "food")

    confusions = model_stats(session)["corrections"]["confusions"]
    assert confusions[0] == {
        "from_category": "shopping",
        "to_category": "food",
        "count": 3,
    }


def test_a_user_correction_is_not_counted_as_a_model_confusion(session):
    """Overruling a rule says nothing about the classifier."""
    row = add(session, "unknown", "other", SOURCE_NONE)
    correct(session, row, "food")

    stats = model_stats(session)
    assert stats["corrections"]["total"] == 1
    assert stats["corrections"]["confusions"] == []


def test_a_rule_row_that_no_rule_matched_is_not_counted_as_coverage(session):
    """No keyword rule targets the fallback category, so this pairing is
    decisive: the label did not come from a rule, whatever the column says."""
    add(session, "genuine match", "food", SOURCE_RULE)
    add(session, "nothing matched this", "other", SOURCE_RULE)

    stats = model_stats(session)
    sources = {row["source"]: row["count"] for row in stats["by_source"]}

    assert sources[SOURCE_RULE] == 1
    assert sources[SOURCE_NONE] == 1
    assert stats["stale_rule_rows"] == 1
    # And it must not count towards what the next retrain can learn from.
    assert stats["trainable_rows"] == 1


def test_training_readiness_counts_only_trainable_rows(session):
    """Model-labelled rows are the model's own output, not evidence."""
    add(session, "a", "food", SOURCE_RULE)
    add(session, "b", "food", SOURCE_USER)
    add(session, "c", "food", SOURCE_MODEL, confidence=0.9)

    stats = model_stats(session)
    assert stats["trainable_rows"] == 2
    assert stats["can_train"] is False  # below MIN_TRAINING_ROWS
