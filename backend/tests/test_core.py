"""Tests for the parsing and categorization logic.

Run with:  pytest
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.pipeline.s10_anomalies import detect_anomalies, _format_inr          # noqa: E402
from app.pipeline.s08_rules import categorize_by_rules                   # noqa: E402
from app.pipeline.s05_normalize import normalize_description             # noqa: E402
from app.pipeline.s07_parser import (                                    # noqa: E402
    UnparseableStatement,
    parse_amount,
    parse_date,
    parse_statement,
)


# --- CSV shape A: two amount columns, junk header, DD/MM/YYYY -------------

SHAPE_A = b"""Statement of Account
Account Number:,XXXX8891

Txn Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/04/2026,UPI/DR/123456789012/SWIGGY/HDFC/swiggy@icici/Pay,"450.00",,"44,550.00"
03/04/2026,NEFT-ACME SALARY-998877,,"25,000.00","69,550.00"
05/04/2026,BAD ROW,abc,,
,,,,
Closing Balance,,,,"69,550.00"
"""

# --- CSV shape B: single signed amount column, DD-MM-YYYY -----------------

SHAPE_B = b"""Date,Description,Amount
01-04-2026,AMAZON PAY INDIA ORDER,-1250.75
02-04-2026,SALARY CREDIT APRIL,32000
03-04-2026,UBER INDIA TRIP,-289.50
"""

# --- CSV shape C: alias names + Dr/Cr indicator + ISO dates ---------------

SHAPE_C = b"""Value Date,Particulars,Amount,Dr/Cr
2026-04-01,POS 4512XXXXXXXX0001 DMART PATIALA,"2,340.00",DR
2026-04-02,INT.CR SAVINGS INTEREST,150.00,CR
"""


def test_shape_a_two_columns():
    transactions, skipped = parse_statement(SHAPE_A)
    assert len(transactions) == 2
    assert skipped == 2            # the bad row and the footer
    assert transactions[0]["direction"] == "debit"
    assert transactions[0]["amount"] == "450.00"
    assert transactions[1]["direction"] == "credit"
    assert transactions[1]["amount"] == "25000.00"


def test_shape_b_signed_amount():
    transactions, skipped = parse_statement(SHAPE_B)
    assert len(transactions) == 3
    assert transactions[0]["direction"] == "debit"      # negative -> money out
    assert transactions[0]["amount"] == "1250.75"
    assert transactions[1]["direction"] == "credit"


def test_shape_c_aliases_and_indicator():
    transactions, _ = parse_statement(SHAPE_C)
    assert len(transactions) == 2
    assert transactions[0]["direction"] == "debit"
    assert transactions[0]["amount"] == "2340.00"
    assert transactions[1]["direction"] == "credit"


def test_missing_header_raises_with_detected_columns():
    with pytest.raises(UnparseableStatement) as error:
        parse_statement(b"Foo,Bar,Baz\n1,2,3\n")
    assert error.value.detected_columns == ["Foo", "Bar", "Baz"]


def test_parser_never_raises_on_bad_rows():
    messy = SHAPE_A + b"\n99/99/9999,GARBAGE,,,\nxx,,,,\n"
    transactions, skipped = parse_statement(messy)
    assert len(transactions) == 2
    assert skipped >= 3


def test_fingerprint_is_stable_for_identical_rows():
    first, _ = parse_statement(SHAPE_B)
    second, _ = parse_statement(SHAPE_B)
    assert [t["fingerprint"] for t in first] == [t["fingerprint"] for t in second]
    assert len({t["fingerprint"] for t in first}) == 3


# --- amounts and dates ----------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,25,000.50", "125000.50"),
        ("₹450", "450"),
        ("(200)", "-200"),
        ("-300.25", "-300.25"),
        ("2,340.00", "2340.00"),
    ],
)
def test_parse_amount(raw, expected):
    assert str(parse_amount(raw)) == expected


@pytest.mark.parametrize("raw", ["", "-", "nil", "abc", None])
def test_parse_amount_rejects_junk(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize(
    "raw,iso",
    [
        ("01/04/2026", "2026-04-01"),
        ("01-04-2026", "2026-04-01"),
        ("2026-04-01", "2026-04-01"),
        ("01 Apr 2026", "2026-04-01"),
    ],
)
def test_parse_date_formats(raw, iso):
    assert parse_date(raw).isoformat() == iso


def test_parse_date_rejects_junk():
    assert parse_date("99/99/9999") is None


# --- normalizer -----------------------------------------------------------

def test_normalizer_keeps_merchant_when_there_are_no_spaces():
    # regression: a greedy \S+@\S+ used to swallow the whole narration
    result = normalize_description("UPI/DR/566223197902/BLINKIT/HDFC/blinkit@ybl/Groceries")
    assert "blinkit" in result


def test_normalizer_strips_rails_and_reference_numbers():
    result = normalize_description("NEFT-AXISCN0123456789-RENT MARCH")
    assert "0123456789" not in result
    assert "rent" in result


def test_normalizer_handles_empty_input():
    assert normalize_description("") == ""
    assert normalize_description(None) == ""


# --- rules ----------------------------------------------------------------

@pytest.mark.parametrize(
    "description,category",
    [
        ("swiggy pay", "food"),
        ("blinkit groceries", "groceries"),
        ("uber india ride", "transport"),
        ("amazon pay india order", "shopping"),
        ("pspcl electricity bill", "bills_utilities"),
        ("house rent march", "rent"),
        ("netflix india subscription", "entertainment"),
        ("apollo pharmacy medicines", "health"),
        ("udemy online course", "education"),
        ("techcadd solutions salary", "income"),
    ],
)
def test_rules_match_known_merchants(description, category):
    assert categorize_by_rules(description) == category


def test_rules_return_none_when_nothing_matches():
    assert categorize_by_rules("qwerty zxcvb") is None
    assert categorize_by_rules("") is None


def test_rent_does_not_match_inside_another_word():
    # word boundaries matter: 'current' must not be read as 'rent'
    assert categorize_by_rules("current account charges") != "rent"


# --- anomalies ------------------------------------------------------------

def test_no_anomalies_without_enough_history():
    transactions = [
        {"date": "2026-08-01", "amount": "5000.00", "direction": "debit", "category": "food"}
    ]
    assert detect_anomalies(transactions) == []


def test_detects_a_clear_outlier():
    transactions = [
        {"date": f"2026-07-{day:02d}", "amount": "300.00", "direction": "debit", "category": "food"}
        for day in range(1, 15)
    ]
    transactions.append(
        {"date": "2026-07-20", "amount": "9000.00", "direction": "debit", "category": "food"}
    )
    flagged = detect_anomalies(transactions, today=__import__("datetime").date(2026, 8, 1))
    assert len(flagged) == 1
    assert flagged[0]["amount"] == "9000.00"
    assert "usual" in flagged[0]["reason"]


@pytest.mark.parametrize(
    "amount,formatted",
    [(125000.5, "1,25,000.50"), (999, "999.00"), (1234, "1,234.00"), (10000000, "1,00,00,000.00")],
)
def test_indian_number_formatting(amount, formatted):
    assert _format_inr(amount) == formatted


# --- refunds are not income (§35) -----------------------------------------


def test_a_refund_is_its_own_category_not_income():
    """Money coming back is not money earned.

    Labelled 'income', a returned ₹5,000 purchase showed as ₹5,000 earned —
    inflating the savings rate, the health score and the income forecast with it.
    """
    for narration in ("refund amazon return", "cashback paytm",
                      "reversal upi", "chargeback hdfc"):
        assert categorize_by_rules(narration) == "refund", narration


def test_real_income_is_still_income():
    for narration in ("salary techcadd", "interest credit", "dividend hdfc"):
        assert categorize_by_rules(narration) == "income", narration
