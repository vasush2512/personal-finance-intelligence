"""Tests for reading statements in formats other than CSV.

The point of the format layer is that only the reading changes. So most of
these assert that a statement expressed as JSON or Excel produces exactly
what the same statement as CSV produces — same amounts, same directions,
same fingerprints.
"""

import datetime as dt
import io
import json
from decimal import Decimal

import pytest

from app.services.parser import UnparseableStatement, parse_statement
from app.services.readers import UnreadableFile, detect_format, read_rows

CSV_BYTES = b"""Date,Narration,Withdrawal Amt.,Deposit Amt.
05/05/2026,UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl,409.50,
06/05/2026,NEFT-AXIS-SALARY MAY,,"1,20,000.00"
"""

JSON_RECORDS = json.dumps(
    [
        {
            "Date": "05/05/2026",
            "Narration": "UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl",
            "Withdrawal Amt.": "409.50",
            "Deposit Amt.": "",
        },
        {
            "Date": "06/05/2026",
            "Narration": "NEFT-AXIS-SALARY MAY",
            "Withdrawal Amt.": "",
            "Deposit Amt.": "1,20,000.00",
        },
    ]
).encode()

JSON_WRAPPED = json.dumps(
    {
        "account": "XXXX1234",
        "transactions": [
            {
                "date": "2026-05-05",
                "description": "UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl",
                "amount": -409.50,
            }
        ],
    }
).encode()


def excel_bytes(rows):
    """Build a real .xlsx in memory from a list of rows."""
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --- format detection -----------------------------------------------------

def test_detects_csv():
    assert detect_format(CSV_BYTES, "statement.csv") == "delimited"


def test_detects_json_by_extension():
    assert detect_format(JSON_RECORDS, "statement.json") == "json"


def test_detects_json_without_an_extension():
    """A renamed file still gets read correctly."""
    assert detect_format(JSON_RECORDS, "statement.txt") == "json"


def test_detects_excel_by_its_bytes():
    """An .xlsx is a zip. The magic number decides, not the name."""
    data = excel_bytes([["Date", "Narration", "Amount"]])
    assert detect_format(data, "statement.csv") == "excel"


# --- json -----------------------------------------------------------------

def test_json_produces_the_same_transactions_as_csv():
    from_csv, _ = parse_statement(CSV_BYTES, "statement.csv")
    from_json, _ = parse_statement(JSON_RECORDS, "statement.json")

    assert [row["amount"] for row in from_json] == [row["amount"] for row in from_csv]
    assert [row["direction"] for row in from_json] == [
        row["direction"] for row in from_csv
    ]


def test_the_same_statement_fingerprints_identically_in_both_formats():
    """Uploading the CSV and then the JSON must not double-count anything."""
    from_csv, _ = parse_statement(CSV_BYTES, "statement.csv")
    from_json, _ = parse_statement(JSON_RECORDS, "statement.json")

    assert [row["fingerprint"] for row in from_json] == [
        row["fingerprint"] for row in from_csv
    ]


def test_json_wrapped_in_an_envelope():
    transactions, _ = parse_statement(JSON_WRAPPED, "statement.json")

    assert len(transactions) == 1
    assert transactions[0]["amount"] == "409.50"
    assert transactions[0]["direction"] == "debit"  # negative means money out


def test_json_column_names_go_through_the_same_aliases():
    """'description' and 'Narration' both land in the description column."""
    payload = json.dumps(
        [{"txn date": "05/05/2026", "particulars": "SWIGGY", "amount": "-409.50"}]
    ).encode()

    transactions, _ = parse_statement(payload, "statement.json")

    assert transactions[0]["description"] == "SWIGGY"


def test_json_keeps_fields_missing_from_the_first_record():
    """Exports omit null fields; the column must not vanish because of it."""
    payload = json.dumps(
        [
            {"date": "05/05/2026", "description": "SWIGGY", "debit": "409.50"},
            {"date": "06/05/2026", "description": "SALARY", "credit": "50000.00"},
        ]
    ).encode()

    transactions, _ = parse_statement(payload, "statement.json")

    assert len(transactions) == 2
    assert transactions[1]["direction"] == "credit"


def test_a_nested_value_does_not_crash_the_import():
    payload = json.dumps(
        [
            {
                "date": "05/05/2026",
                "description": "SWIGGY",
                "amount": "-409.50",
                "meta": {"channel": "upi"},
            }
        ]
    ).encode()

    transactions, _ = parse_statement(payload, "statement.json")
    assert len(transactions) == 1


def test_invalid_json_is_reported_not_raised_raw():
    with pytest.raises(UnparseableStatement) as error:
        parse_statement(b"{not json at all", "statement.json")

    assert "not valid JSON" in str(error.value)


def test_json_of_the_wrong_shape_explains_itself():
    with pytest.raises(UnparseableStatement) as error:
        parse_statement(b'{"balance": 100}', "statement.json")

    assert "list of transactions" in str(error.value)


# --- excel ----------------------------------------------------------------

def test_excel_produces_the_same_transactions_as_csv():
    data = excel_bytes(
        [
            ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."],
            ["05/05/2026", "UPI/DR/412345678901/SWIGGY/HDFC/swiggy@ybl", "409.50", ""],
            ["06/05/2026", "NEFT-AXIS-SALARY MAY", "", "1,20,000.00"],
        ]
    )

    from_csv, _ = parse_statement(CSV_BYTES, "statement.csv")
    from_excel, _ = parse_statement(data, "statement.xlsx")

    assert [row["fingerprint"] for row in from_excel] == [
        row["fingerprint"] for row in from_csv
    ]


def test_excel_native_dates_and_numbers():
    """Excel gives back real datetimes and floats, not text."""
    data = excel_bytes(
        [
            ["Date", "Narration", "Amount"],
            [dt.datetime(2026, 5, 5), "SWIGGY ORDER", -409.5],
        ]
    )

    transactions, _ = parse_statement(data, "statement.xlsx")

    assert transactions[0]["date"] == "2026-05-05"
    assert transactions[0]["amount"] == "409.50"
    assert transactions[0]["direction"] == "debit"


def test_excel_junk_above_the_header_is_skipped():
    data = excel_bytes(
        [
            ["Statement of Account", "", ""],
            ["Account Number", "XXXX1234", ""],
            ["", "", ""],
            ["Date", "Narration", "Amount"],
            ["05/05/2026", "SWIGGY ORDER", "-409.50"],
        ]
    )

    transactions, _ = parse_statement(data, "statement.xlsx")

    assert len(transactions) == 1


def test_a_corrupt_excel_file_is_reported_cleanly():
    with pytest.raises(UnparseableStatement):
        parse_statement(b"PK\x03\x04 and then nonsense", "statement.xlsx")


# --- shared behaviour -----------------------------------------------------

def test_an_empty_file_of_any_format_is_rejected():
    with pytest.raises(UnreadableFile):
        read_rows(b"", "statement.json")


def test_amounts_never_become_floats():
    transactions, _ = parse_statement(JSON_WRAPPED, "statement.json")
    assert Decimal(transactions[0]["amount"]) == Decimal("409.50")
