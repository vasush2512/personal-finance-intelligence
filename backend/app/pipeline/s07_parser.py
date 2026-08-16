"""Parse a real-world bank statement into clean transaction dicts.

Design rule from the PRD: this module NEVER raises on a bad row. Rows that
cannot be parsed are counted and skipped. Only a file whose header cannot be
found at all raises, and that error carries the column names we did detect so
the UI can offer manual mapping.

Reading the file into rows is services/readers.py's job, so this module is
the same whether the upload was CSV, JSON or Excel.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.pipeline.s05_normalize import fingerprint, normalize_description
from app.pipeline.s06_readers import UnreadableFile, read_sheets

# --- column aliases -------------------------------------------------------

DATE_ALIASES = {
    "date", "txn date", "transaction date", "value date", "value dt",
    "tran date", "post date", "booking date", "date of transaction",
}
DESC_ALIASES = {
    "description", "narration", "particulars", "remarks", "details",
    "transaction details", "transaction remarks", "narrative", "text",
}
DEBIT_ALIASES = {
    "withdrawal amt", "withdrawal amount", "withdrawal", "debit", "debit amount",
    "dr", "dr amount", "withdrawal amt.", "paid out", "money out",
}
CREDIT_ALIASES = {
    "deposit amt", "deposit amount", "deposit", "credit", "credit amount",
    "cr", "cr amount", "deposit amt.", "paid in", "money in",
}
AMOUNT_ALIASES = {"amount", "amt", "transaction amount", "txn amount", "value"}
TYPE_ALIASES = {"type", "dr/cr", "cr/dr", "transaction type", "debit/credit", "indicator"}

DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%m/%d/%Y", "%Y/%m/%d",
]

HEADER_SCAN_LINES = 25


class UnparseableStatement(Exception):
    """Raised when no header row can be found. Carries what we did see."""

    def __init__(self, message, detected_columns=None):
        super().__init__(message)
        self.detected_columns = detected_columns or []


# --- small helpers --------------------------------------------------------

def _clean_header(cell: str) -> str:
    """Normalize a header cell so 'Withdrawal Amt.' matches 'withdrawal amt'."""
    text = str(cell or "").strip().lower()
    text = text.replace("(inr)", "").replace("(rs)", "").replace("₹", "")
    text = re.sub(r"[^a-z0-9/ .]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(".")


def parse_amount(value):
    """'1,25,000.50' / '₹450' / '(200)' / '-300' -> Decimal, or None."""
    if value is None:
        return None

    # Excel and JSON give real numbers. Route them through str() rather than
    # Decimal(float), which would faithfully reproduce the float's error.
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = repr(value)

    text = str(value).strip()
    if not text or text.lower() in {"-", "nan", "none", "null", "nil"}:
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace("₹", "").replace("rs.", "").replace("rs", "")
    text = text.replace(",", "").replace(" ", "")
    text = re.sub(r"(cr|dr)$", "", text, flags=re.IGNORECASE)

    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return -amount if negative else amount


def parse_date(value):
    """Try every known format. Returns a date, or None."""
    if value is None:
        return None

    # Excel hands back real datetimes rather than text, and so does a JSON
    # reader that has already been given a date object. Take them as they are
    # instead of formatting them just to parse them again.
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    text = text.split(" ")[0] if len(text.split(" ")) > 1 and ":" in text else text

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# --- header detection -----------------------------------------------------

def _score_header(cells):
    """How much does this row look like a header? Needs a date and a desc."""
    cleaned = {_clean_header(c) for c in cells if str(c).strip()}
    has_date = bool(cleaned & DATE_ALIASES)
    has_desc = bool(cleaned & DESC_ALIASES)
    has_money = bool(cleaned & (DEBIT_ALIASES | CREDIT_ALIASES | AMOUNT_ALIASES))
    if not (has_date and has_desc):
        return 0
    return 2 + int(has_money)


def find_header_row(rows):
    """Scan the first N rows for the real header. Returns (index, cells)."""
    best_index, best_score = -1, 0
    for index, cells in enumerate(rows[:HEADER_SCAN_LINES]):
        score = _score_header(cells)
        if score > best_score:
            best_index, best_score = index, score
    if best_index == -1:
        seen = [str(c).strip() for c in (rows[0] if rows else []) if str(c).strip()]
        raise UnparseableStatement(
            "Could not find a header row with a date and a description column.",
            detected_columns=seen,
        )
    return best_index, rows[best_index]


def map_columns(header_cells):
    """Map cleaned header names to their column index."""
    mapping = {}
    for index, cell in enumerate(header_cells):
        name = _clean_header(cell)
        if not name:
            continue
        if name in DATE_ALIASES and "date" not in mapping:
            mapping["date"] = index
        elif name in DESC_ALIASES and "description" not in mapping:
            mapping["description"] = index
        elif name in DEBIT_ALIASES and "debit" not in mapping:
            mapping["debit"] = index
        elif name in CREDIT_ALIASES and "credit" not in mapping:
            mapping["credit"] = index
        elif name in AMOUNT_ALIASES and "amount" not in mapping:
            mapping["amount"] = index
        elif name in TYPE_ALIASES and "type" not in mapping:
            mapping["type"] = index
    return mapping


# --- row parsing ----------------------------------------------------------

def _cell(row, index):
    if index is None or index >= len(row):
        return ""
    return row[index]


def _resolve_money(row, columns):
    """Return (amount, direction) or (None, None) if the row has no money."""
    debit = parse_amount(_cell(row, columns.get("debit")))
    credit = parse_amount(_cell(row, columns.get("credit")))

    # Two-column layout (most Indian banks)
    if debit is not None and debit != 0:
        return abs(debit), "debit"
    if credit is not None and credit != 0:
        return abs(credit), "credit"

    # Single signed amount column
    amount = parse_amount(_cell(row, columns.get("amount")))
    if amount is None or amount == 0:
        return None, None

    marker = str(_cell(row, columns.get("type"))).strip().lower()
    if marker.startswith("cr") or marker in {"credit", "deposit", "c"}:
        return abs(amount), "credit"
    if marker.startswith("dr") or marker in {"debit", "withdrawal", "d"}:
        return abs(amount), "debit"

    # No type column: negative means money out
    return abs(amount), ("credit" if amount > 0 else "debit")


def parse_rows(rows, columns):
    """Parse data rows. Returns (transactions, skipped_count)."""
    transactions, skipped = [], 0

    for row in rows:
        if not any(str(cell).strip() for cell in row):
            continue

        date = parse_date(_cell(row, columns.get("date")))
        raw_description = str(_cell(row, columns.get("description"))).strip()
        amount, direction = _resolve_money(row, columns)

        if date is None or not raw_description or amount is None:
            skipped += 1          # summary lines, footers, malformed rows
            continue

        normalized = normalize_description(raw_description)
        amount_str = f"{amount:.2f}"
        transactions.append(
            {
                "date": date.isoformat(),
                "description": raw_description,
                "normalized_description": normalized,
                "amount": amount_str,
                "direction": direction,
                "fingerprint": fingerprint(date.isoformat(), normalized, amount_str, direction),
            }
        )

    return transactions, skipped


def parse_statement(file_bytes, filename=None):
    """Entry point. bytes -> (transactions, skipped_count).

    The file may be CSV, JSON or Excel; services/readers.py works out which
    and hands back one table per sheet. Everything from here down is
    format-blind.

    A workbook with one month per tab is imported in full. Sheets that are
    not transaction tables — a cover page, a summary tab — have no header row
    and are passed over rather than failing the upload.

    Raises UnparseableStatement only when the file cannot be read at all, or
    when no sheet in it holds a transaction table. Bad individual rows are
    counted, never raised.
    """
    try:
        sheets = read_sheets(file_bytes, filename)
    except UnreadableFile as error:
        raise UnparseableStatement(str(error), detected_columns=error.detected_columns)

    transactions, skipped = [], 0
    first_failure = None

    for name, rows in sheets:
        try:
            sheet_transactions, sheet_skipped = parse_sheet(rows)
        except UnparseableStatement as error:
            first_failure = first_failure or error
            continue
        # Remember which tab each row came from, so the UI can filter by it.
        for transaction in sheet_transactions:
            transaction["sheet_name"] = name
        transactions.extend(sheet_transactions)
        skipped += sheet_skipped

    # Every sheet was unreadable, so the file really is the wrong shape.
    if not transactions and first_failure is not None:
        raise first_failure

    return transactions, skipped


def parse_sheet(rows):
    """One table of rows -> (transactions, skipped_count)."""
    header_index, header_cells = find_header_row(rows)
    columns = map_columns(header_cells)

    missing = {"date", "description"} - set(columns)
    if missing:
        raise UnparseableStatement(
            f"Missing required column(s): {', '.join(sorted(missing))}",
            detected_columns=[str(c).strip() for c in header_cells if str(c).strip()],
        )
    if not ({"debit", "credit"} & set(columns)) and "amount" not in columns:
        raise UnparseableStatement(
            "Could not find an amount column.",
            detected_columns=[str(c).strip() for c in header_cells if str(c).strip()],
        )

    return parse_rows(rows[header_index + 1:], columns)
