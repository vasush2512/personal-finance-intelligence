"""Database side of anomaly detection.

app/ml/anomalies.py does the statistics on plain dicts and knows nothing
about SQLAlchemy. This module feeds it and maps the result back.

Anomalies are computed per request rather than stored. The flag depends on a
trailing six-month window, so a charge that looks extraordinary today stops
being one once similar charges arrive. A stored column would quietly go
stale, and nothing would ever recompute it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.anomalies import detect_anomalies
from app.models import Transaction


def as_plain_rows(session: Session):
    """Every transaction, in the shape detect_anomalies expects."""
    transactions = session.execute(select(Transaction)).scalars().all()
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


def find_anomalies(session: Session, today=None):
    """Unusually large debits, newest first, each with a readable reason."""
    return detect_anomalies(as_plain_rows(session), today=today)
