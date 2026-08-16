"""Merchant extraction and explainable anomaly scoring (Phase 1).

Both are pure functions over plain values, so none of this needs a database or
a server — which is the point of keeping them in app/pipeline/.
"""

import pytest

from app.pipeline.s05_normalize import (
    extract_merchant,
    extract_payment_method,
    normalize_description,
)
from app.pipeline.s10_anomalies import score_transaction

# --- merchant extraction --------------------------------------------------


@pytest.mark.parametrize(
    "narration, expected",
    [
        ("UPI/DR/998877665544/SWIGGY/HDFC/swiggy@icici/Payment", "Swiggy"),
        ("POS 4512XXXXXXXX1234 AMAZON PAY INDIA        MUMBAI", "Amazon Pay India"),
        ("UPI/DR/320678652213/BLINKIT/HDFC/blinkit@ybl/Groceries", "Blinkit"),
        # 'rent' is a purpose tag, but it is also all this narration says, so
        # the first word is kept rather than returning nothing.
        ("NEFT-AXISCN0123456789-RENT MARCH", "Rent"),
    ],
)
def test_merchant_is_pulled_out_of_the_narration(narration, expected):
    assert extract_merchant(narration) == expected


def test_trailing_purpose_tags_are_not_part_of_the_merchant():
    """UPI narrations append what the payment was for. That is not a shop."""
    assert extract_merchant("UPI/DR/1/BLINKIT/HDFC/x@ybl/Groceries") == "Blinkit"
    assert extract_merchant("UPI/DR/2/UDEMY/HDFC/x@ybl/Education") == "Udemy"


def test_leading_filler_words_are_not_the_merchant():
    """'Payment' leads a lot of narrations and names no one."""
    assert extract_merchant("UPI/DR/123456/PAYMENT/DMART/HDFC") == "Dmart"


def test_merchant_keeps_multi_word_names_together():
    """'Reliance Fresh' is a shop; 'Reliance' on its own is a different one."""
    assert extract_merchant("POS 1234 RELIANCE FRESH STORE") == "Reliance Fresh Store"


def test_merchant_never_returns_empty():
    """A narration that normalizes to nothing still has to render."""
    assert extract_merchant("UPI/HDFC/1234567890") == "Unknown"
    assert extract_merchant("") == "Unknown"


def test_merchant_accepts_a_precomputed_normalized_form():
    """Rows out of the database already have one; do not redo the work."""
    narration = "UPI/DR/998877665544/SWIGGY/HDFC/swiggy@icici/Payment"
    normalized = normalize_description(narration)
    assert extract_merchant(narration, normalized) == "Swiggy"


# --- payment method -------------------------------------------------------


@pytest.mark.parametrize(
    "narration, expected",
    [
        ("UPI/DR/998877665544/SWIGGY/HDFC", "UPI"),
        ("POS 4512XXXXXXXX1234 AMAZON", "Card"),
        ("NEFT-AXISCN0123456789-RENT", "NEFT"),
        ("ATM WDL 1234 DELHI", "ATM"),
        ("ACH DR LIC PREMIUM", "Auto-debit"),
    ],
)
def test_payment_method_is_read_from_the_rail(narration, expected):
    assert extract_payment_method(narration) == expected


def test_payment_method_is_none_when_nothing_says():
    assert extract_payment_method("SOME PLAIN DESCRIPTION") is None
    assert extract_payment_method("") is None


# --- anomaly scoring ------------------------------------------------------


def test_a_typical_amount_scores_low():
    peers = [400, 380, 420, 390, 410, 395, 405, 415]
    report = score_transaction(400, peers)
    assert report["score"] < 30


def test_a_wildly_large_amount_scores_high():
    peers = [400, 380, 420, 390, 410, 395, 405, 415]
    report = score_transaction(9400, peers)
    assert report["score"] > 70
    assert report["ratio"] > 20


def test_score_is_bounded_at_both_ends():
    peers = [400, 380, 420, 390, 410]
    for amount in (1, 400, 1_000_000):
        score = score_transaction(amount, peers)["score"]
        assert 0 <= score <= 100


def test_no_peers_means_no_score_rather_than_a_guess():
    report = score_transaction(9400, [])
    assert report["score"] == 0
    assert report["factors"] == []
    assert report["baseline"] is None


def test_identical_peers_still_produce_a_score():
    """A fixed subscription has zero spread; sigma cannot speak, ratio can."""
    peers = [649] * 8
    report = score_transaction(6490, peers)
    assert report["score"] > 50
    amount_factor = next(f for f in report["factors"] if f["key"] == "amount")
    assert "identical" in amount_factor["detail"]


def test_merchant_history_adds_a_factor():
    peers = [400, 380, 420, 390, 410, 395, 405, 415]
    without = score_transaction(2000, peers)
    with_merchant = score_transaction(2000, peers, merchant_amounts=[390, 400, 410])

    keys = {factor["key"] for factor in with_merchant["factors"]}
    assert "merchant" in keys
    assert "merchant" not in {factor["key"] for factor in without["factors"]}


def test_too_little_merchant_history_is_left_out():
    """Two prior transactions cannot describe what you usually pay someone."""
    peers = [400, 380, 420, 390, 410, 395, 405, 415]
    report = score_transaction(2000, peers, merchant_amounts=[390, 400])
    assert "merchant" not in {factor["key"] for factor in report["factors"]}


def test_a_familiar_merchant_scores_lower_on_frequency():
    peers = [400, 380, 420, 390, 410, 395, 405, 415]
    stranger = score_transaction(2000, peers, merchant_amounts=[])
    regular = score_transaction(2000, peers, merchant_amounts=[390, 400, 410, 405])

    def frequency(report):
        return next(f for f in report["factors"] if f["key"] == "frequency")["value"]

    assert frequency(stranger) > frequency(regular)


def test_every_factor_reports_on_the_same_scale():
    peers = [400, 380, 420, 390, 410, 395, 405, 415]
    report = score_transaction(3000, peers, merchant_amounts=[390, 400, 410])

    for factor in report["factors"]:
        assert 0 <= factor["value"] <= 100
        assert factor["label"] and factor["detail"]
