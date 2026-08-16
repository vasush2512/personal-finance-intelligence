"""Database side of duplicate and recurring detection.

Both detectors in app/pipeline/ work on plain dicts and know nothing about
SQLAlchemy. This module feeds them and maps the results back, the same way
s14_anomaly_service does for the anomaly detector.

Neither result is stored. Both depend on a trailing window, so a stored flag
would go stale the moment new rows arrived and nothing would recompute it. What
*is* stored is the user's verdict on a suggested duplicate — a human decision
has to survive, or the panel keeps asking about pairs already dismissed.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s04_models import DuplicateVerdict, Transaction
from app.pipeline.s05_normalize import extract_merchant, extract_payment_method
from app.pipeline.s10b_duplicates import find_duplicates
from app.pipeline.s10c_recurring import find_recurring, monthly_commitment
from app.store.s12_aggregations import source_conditions

# How far back both detectors look. Longer than the anomaly window because a
# yearly subscription cannot be recognised inside six months.
LOOKBACK_DAYS = 730

# A hard ceiling on what the duplicates endpoint returns. On a hundred thousand
# rows a genuinely repetitive dataset can produce thousands of candidate pairs,
# and a list nobody can finish is not a review queue.
MAX_PAIRS = 200


def _rows(session: Session, today=None, direction=None, **source):
    """Transactions in the window, in the shape the detectors expect."""
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=LOOKBACK_DAYS)

    conditions = [Transaction.date >= cutoff, *source_conditions(**source)]
    if direction:
        conditions.append(Transaction.direction == direction)

    # The seven columns the detectors read, not whole ORM objects. Over a
    # thirty-thousand-row window the difference is most of the cost of this
    # call: an entity has to be constructed, registered in the identity map
    # and kept alive for the session, and none of that is used here — these
    # rows become plain dicts on the next line.
    rows = session.execute(
        select(
            Transaction.id,
            Transaction.date,
            Transaction.description,
            Transaction.normalized_description,
            Transaction.amount,
            Transaction.direction,
            Transaction.category,
        ).where(*conditions)
    ).all()

    return [
        {
            "id": row.id,
            "date": row.date,
            "description": row.description,
            "merchant": extract_merchant(row.description, row.normalized_description),
            "payment_method": extract_payment_method(row.description),
            "amount": float(row.amount),
            "direction": row.direction,
            "category": row.category,
        }
        for row in rows
    ]


def _decided_pairs(session: Session, user_id=None):
    """{(first_id, second_id): is_duplicate} for everything already answered."""
    rows = session.execute(
        select(
            DuplicateVerdict.first_id,
            DuplicateVerdict.second_id,
            DuplicateVerdict.is_duplicate,
        )
        .join(Transaction, Transaction.id == DuplicateVerdict.first_id)
        .where(*([Transaction.user_id == user_id] if user_id is not None else []))
    ).all()
    return {(first, second): verdict for first, second, verdict in rows}


def duplicate_pairs(session: Session, today=None, include_decided=False, **source):
    """Suggested duplicate pairs, strongest first, with any verdict attached."""
    pairs = find_duplicates(_rows(session, today, **source), limit=MAX_PAIRS)
    decided = _decided_pairs(session, source.get("user_id"))

    results = []
    for pair in pairs:
        key = _pair_key(pair["first"]["id"], pair["second"]["id"])
        verdict = decided.get(key)

        # A pair the user has already ruled on drops out of the queue unless
        # explicitly asked for — the point of recording the answer is not
        # having to give it twice.
        if verdict is not None and not include_decided:
            continue

        results.append({
            "first": pair["first"],
            "second": pair["second"],
            "score": pair["score"],
            "reasons": pair["reasons"],
            "days_apart": pair["days_apart"],
            "amount": pair["amount"],
            "merchant": pair["merchant"],
            "verdict": verdict,
        })

    return results


def record_verdict(session: Session, first_id: int, second_id: int, is_duplicate: bool, user_id=None):
    """Store what the user decided about a pair. Idempotent.

    Returns None when either id does not exist, so the router can 404 instead
    of writing a verdict about transactions that are not there.
    """
    first_key, second_key = _pair_key(first_id, second_id)

    for identifier in (first_key, second_key):
        row = session.get(Transaction, identifier)
        # Another user's transaction is treated as absent, so this cannot be
        # used to record verdicts about — or probe for — rows outside the
        # caller's own data.
        if row is None or (user_id is not None and row.user_id != user_id):
            return None

    existing = session.execute(
        select(DuplicateVerdict).where(
            DuplicateVerdict.first_id == first_key,
            DuplicateVerdict.second_id == second_key,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = DuplicateVerdict(
            first_id=first_key, second_id=second_key, is_duplicate=is_duplicate
        )
        session.add(existing)
    else:
        # Changing your mind has to be possible; the row is the current answer,
        # not an append-only log.
        existing.is_duplicate = is_duplicate

    session.commit()
    session.refresh(existing)
    return existing


def _pair_key(first_id: int, second_id: int):
    """Lowest id first, so a pair has one identity however it was compared."""
    return (min(first_id, second_id), max(first_id, second_id))


def recurring_payments(session: Session, today=None, **source):
    """Merchants being paid on a regular rhythm, plus the monthly total."""
    today = today or dt.date.today()
    detected = find_recurring(_rows(session, today, direction="debit", **source))

    return {
        "payments": detected,
        "monthly_total": monthly_commitment(detected),
        "lookback_days": LOOKBACK_DAYS,
    }
