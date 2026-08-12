"""Turn an uploaded CSV into stored rows.

The parsing itself lives in parser.py. This module owns the database side:
dropping rows we have already seen, writing the Upload record, and reporting
the counts back.

Rows are categorized on the way in, by the keyword rules in app/ml. The
route handler never touches that code — it calls import_statement and the
categorization happens here.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.categorizer import apply_rules
from app.models import Transaction, Upload
from app.services.parser import parse_statement


def find_known_fingerprints(session: Session, fingerprints):
    """Return the subset of these fingerprints already in the database."""
    if not fingerprints:
        return set()

    known = set()
    # SQLite caps how many parameters one statement may carry, so ask in
    # batches rather than building one enormous IN clause.
    batch_size = 500
    fingerprint_list = list(fingerprints)
    for start in range(0, len(fingerprint_list), batch_size):
        batch = fingerprint_list[start : start + batch_size]
        rows = session.execute(
            select(Transaction.fingerprint).where(Transaction.fingerprint.in_(batch))
        ).scalars()
        known.update(rows)
    return known


def split_new_from_duplicates(parsed_rows, known_fingerprints):
    """Return (new_rows, duplicate_count).

    Two kinds of duplicate get dropped: rows already in the database from an
    earlier upload, and rows repeated inside this one file.
    """
    new_rows = []
    seen_in_this_file = set()
    duplicates = 0

    for row in parsed_rows:
        fingerprint = row["fingerprint"]
        if fingerprint in known_fingerprints or fingerprint in seen_in_this_file:
            duplicates += 1
            continue
        seen_in_this_file.add(fingerprint)
        new_rows.append(row)

    return new_rows, duplicates


def import_statement(session: Session, filename: str, file_bytes: bytes) -> dict:
    """Parse, deduplicate, store. Returns the counts for the API response.

    Raises UnparseableStatement (from parser.py) only when no header row can
    be found. Individual bad rows are counted in `skipped`, never raised.
    """
    parsed_rows, skipped = parse_statement(file_bytes)

    known = find_known_fingerprints(session, {row["fingerprint"] for row in parsed_rows})
    new_rows, duplicates = split_new_from_duplicates(parsed_rows, known)

    # Stage 1 of categorization. Sets category / category_source / confidence
    # on each dict in place; anything no rule matches stays 'other'.
    apply_rules(new_rows)

    upload = Upload(
        filename=filename,
        rows_parsed=len(parsed_rows),
        rows_imported=len(new_rows),
        rows_skipped=skipped,
        duplicates=duplicates,
    )
    session.add(upload)
    session.flush()          # assigns upload.id without committing yet

    for row in new_rows:
        session.add(
            Transaction(
                upload_id=upload.id,
                date=_as_date(row["date"]),
                description=row["description"],
                normalized_description=row["normalized_description"],
                amount=row["amount"],
                direction=row["direction"],
                fingerprint=row["fingerprint"],
                category=row["category"],
                category_source=row["category_source"],
                confidence=row["confidence"],
            )
        )

    session.commit()

    return {
        "upload_id": upload.id,
        "filename": upload.filename,
        "rows_parsed": upload.rows_parsed,
        "imported": upload.rows_imported,
        "skipped": upload.rows_skipped,
        "duplicates": upload.duplicates,
    }


def _as_date(value):
    """The parser hands back ISO strings; the DB column wants a date."""
    import datetime as dt

    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)
