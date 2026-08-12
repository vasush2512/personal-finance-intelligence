"""Tests for filtering by where a transaction came from.

The filter options are built from the database, not from a fixed list, so
these check that the options reflect what was actually imported and that
filtering by them returns the right rows.
"""

import datetime as dt
import io
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Transaction
from app.routers.transactions import build_filters
from app.services import aggregations
from app.services.importer import import_statement

HEADER = ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."]

CSV_BYTES = b"""Date,Narration,Withdrawal Amt.,Deposit Amt.
05/05/2026,UPI/DR/1/SWIGGY/HDFC,409.50,
"""


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


def workbook_bytes(sheets):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(title=name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


THREE_TABS = {
    "May": [HEADER, ["11/05/2026", "ZEPTO ORDER", "510.00", ""]],
    "June": [HEADER, ["12/06/2026", "PVR CINEMAS", "980.00", ""]],
    "July": [HEADER, ["13/07/2026", "APOLLO PHARMACY", "1330.00", ""]],
}


# --- what gets stored -----------------------------------------------------

def test_each_row_remembers_its_worksheet(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))

    sheets = session.execute(select(Transaction.sheet_name)).scalars().all()
    assert set(sheets) == {"May", "June", "July"}


def test_csv_rows_have_no_sheet(session):
    """A CSV is one table. Repeating the filename as a sheet would be noise."""
    import_statement(session, "statement.csv", CSV_BYTES)

    sheets = session.execute(select(Transaction.sheet_name)).scalars().all()
    assert sheets == [None]


# --- the options offered --------------------------------------------------

def test_sources_lists_every_sheet_with_its_count(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))

    sources = aggregations.sources(session)

    assert len(sources) == 1
    assert sources[0]["filename"] == "book.xlsx"
    assert sources[0]["count"] == 3
    assert {sheet["sheet_name"] for sheet in sources[0]["sheets"]} == {
        "May",
        "June",
        "July",
    }
    assert all(sheet["count"] == 1 for sheet in sources[0]["sheets"])


def test_sources_covers_several_files(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    import_statement(session, "statement.csv", CSV_BYTES)

    sources = aggregations.sources(session)

    assert {source["filename"] for source in sources} == {"book.xlsx", "statement.csv"}


def test_an_upload_that_imported_nothing_is_not_offered(session):
    """A re-upload is a real event but not a place rows can be filtered to."""
    import_statement(session, "statement.csv", CSV_BYTES)
    import_statement(session, "statement.csv", CSV_BYTES)  # all duplicates

    sources = aggregations.sources(session)

    assert len(sources) == 1
    assert sources[0]["count"] == 1


def test_no_uploads_means_no_options(session):
    assert aggregations.sources(session) == []


# --- filtering by them ----------------------------------------------------

def count_with(session, **kwargs):
    conditions = build_filters(None, None, None, None, **kwargs)
    return len(session.execute(select(Transaction).where(*conditions)).scalars().all())


def test_filtering_to_one_worksheet(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))

    assert count_with(session, sheet="June") == 1
    assert count_with(session, sheet="May") == 1


def test_filtering_to_one_file(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    result = import_statement(session, "statement.csv", CSV_BYTES)

    assert count_with(session, upload_id=result["upload_id"]) == 1


def test_empty_sheet_filter_selects_the_rows_with_no_sheet(session):
    """Otherwise a plain CSV's rows could never be isolated."""
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    import_statement(session, "statement.csv", CSV_BYTES)

    assert count_with(session, sheet="") == 1


def test_no_source_filter_returns_everything(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    import_statement(session, "statement.csv", CSV_BYTES)

    assert count_with(session) == 4


def test_file_and_sheet_filters_combine(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    other = import_statement(session, "statement.csv", CSV_BYTES)

    # The CSV upload has no sheet called June, so this is correctly empty.
    assert count_with(session, upload_id=other["upload_id"], sheet="June") == 0


# --- the whole dashboard follows the filter -------------------------------

def test_totals_follow_the_source_filter(session):
    """The cards must not describe the whole database while the table shows
    one file. That mismatch is worse than having no filter."""
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    csv_upload = import_statement(session, "statement.csv", CSV_BYTES)

    everything = aggregations.summary(session)
    just_csv = aggregations.summary(session, upload_id=csv_upload["upload_id"])

    assert everything["transaction_count"] == 4
    assert just_csv["transaction_count"] == 1
    assert just_csv["total_spent"] < everything["total_spent"]


def test_totals_follow_a_worksheet(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))

    june = aggregations.summary(session, sheet="June")

    assert june["transaction_count"] == 1
    assert june["by_category"][0]["category"] == "entertainment"


def test_the_trend_chart_follows_the_source_filter(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    csv_upload = import_statement(session, "statement.csv", CSV_BYTES)

    scoped = aggregations.monthly_trends(session, upload_id=csv_upload["upload_id"])

    assert [point["month"] for point in scoped] == ["2026-05"]


def test_top_merchants_follow_the_source_filter(session):
    import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))

    merchants = aggregations.top_merchants(session, sheet="July")

    assert [row["merchant"] for row in merchants] == ["apollo"]


def test_an_unknown_source_yields_zeros_not_errors(session):
    import_statement(session, "statement.csv", CSV_BYTES)

    scoped = aggregations.summary(session, upload_id=9999)

    assert scoped["transaction_count"] == 0
    assert scoped["total_spent"] == Decimal("0.00")
    assert scoped["by_category"] == []


def test_deleting_an_upload_removes_it_from_the_options(session):
    from app.models import Upload

    result = import_statement(session, "book.xlsx", workbook_bytes(THREE_TABS))
    session.delete(session.get(Upload, result["upload_id"]))
    session.commit()

    assert aggregations.sources(session) == []
