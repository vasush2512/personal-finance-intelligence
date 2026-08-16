"""Database side of anomaly detection.

app/ml/anomalies.py does the statistics on plain dicts and knows nothing
about SQLAlchemy. This module feeds it and maps the result back.

Anomalies are computed per request rather than stored. The flag depends on a
trailing six-month window, so a charge that looks extraordinary today stops
being one once similar charges arrive. A stored column would quietly go
stale, and nothing would ever recompute it.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pipeline.s10_anomalies import LOOKBACK_DAYS, detect_anomalies
from app.core.s04_models import Transaction
from app.store.s12_aggregations import source_conditions


def as_plain_rows(session: Session, today=None, **source):
    """The rows detect_anomalies can actually use, in the shape it expects.

    Only debits inside the lookback window matter — the detector discards
    everything else on its first pass. Filtering in SQL instead of in Python
    is the difference between reading a hundred thousand rows and reading a
    few hundred.
    """
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=LOOKBACK_DAYS)

    transactions = session.execute(
        select(Transaction).where(
            Transaction.direction == "debit",
            Transaction.date >= cutoff,
            *source_conditions(**source),
        )
    ).scalars().all()

    return [
        {
            "id": row.id,
            "date": row.date.isoformat(),
            "description": row.description,
            "amount": f"{row.amount:.2f}",
            "direction": row.direction,
            "category": row.category,
        }
        for row in transactions
    ]


def find_anomalies(session: Session, today=None, sensitivity=None, **source):
    """Unusually large debits, newest first, each with a readable reason.

    Under a source filter the baselines are computed from that file's rows
    only. That is the honest reading of "is this transaction unusual for
    this statement", but it does mean one month's file judges a charge
    against one month of history — a narrower baseline than the full six.
    """
    return detect_anomalies(
        as_plain_rows(session, today, **source), today=today,
        sensitivity=sensitivity,
    )
