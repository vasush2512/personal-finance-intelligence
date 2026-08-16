"""Everything the transaction detail drawer shows, for one row.

Sits after s14_anomaly_service because it reuses the same window and the same
scoring, for a single transaction rather than the whole set.

The expensive part is the peer set — every other transaction in the same
category over the trailing window — so it is fetched once and reused for both
the category baseline and the merchant baseline.
"""

import datetime as dt

from sqlalchemy import select

from app.core.s04_models import Transaction
from app.pipeline.s05_normalize import extract_merchant, extract_payment_method
from app.pipeline.s10_anomalies import (
    LOOKBACK_DAYS,
    MIN_HISTORY,
    SIGMA,
    _format_inr,
    score_transaction,
)


def _peer_rows(session, transaction, today):
    """Other debits in the same category, inside the trailing window.

    Excludes the transaction itself — a large charge must not be allowed to
    raise the bar it is being measured against.
    """
    cutoff = today - dt.timedelta(days=LOOKBACK_DAYS)

    return session.execute(
        select(Transaction).where(
            Transaction.category == transaction.category,
            Transaction.direction == "debit",
            Transaction.date >= cutoff,
            Transaction.id != transaction.id,
        )
    ).scalars().all()


def transaction_detail(session, transaction_id, today=None, user_id=None):
    """One transaction, with the analysis behind any flag on it.

    Returns None when the id does not exist, so the router can 404 rather than
    this module raising an HTTP concern it should not know about.
    """
    transaction = session.get(Transaction, transaction_id)

    # Another user's row is indistinguishable from a missing one here,
    # so the router's 404 says the same thing for both.
    if transaction is not None and user_id is not None and transaction.user_id != user_id:
        return None
    if transaction is None:
        return None

    today = today or dt.date.today()

    merchant = extract_merchant(
        transaction.description, transaction.normalized_description
    )
    payment_method = extract_payment_method(transaction.description)

    detail = {
        "id": transaction.id,
        "date": transaction.date,
        "description": transaction.description,
        "normalized_description": transaction.normalized_description,
        "merchant": merchant,
        "payment_method": payment_method,
        "amount": transaction.amount,
        "direction": transaction.direction,
        "category": transaction.category,
        "category_source": transaction.category_source,
        "confidence": transaction.confidence,
        "sheet_name": transaction.sheet_name,
        "upload_id": transaction.upload_id,
        "is_anomaly": False,
        "anomaly": None,
    }

    # Only spending is scored. A large salary credit is not an unusual expense,
    # and running it through a spending baseline would say it was.
    if transaction.direction != "debit":
        return detail

    peers = _peer_rows(session, transaction, today)
    if len(peers) < MIN_HISTORY:
        detail["anomaly"] = {
            "available": False,
            "reason": (
                f"Needs at least {MIN_HISTORY} earlier {transaction.category} "
                f"transactions to compare against. There are {len(peers)}."
            ),
        }
        return detail

    peer_amounts = [float(row.amount) for row in peers]

    # This merchant's own history, matched on the normalized narration so
    # "SWIGGY ORDER" and "SWIGGY/BLR" count as the same merchant.
    merchant_amounts = [
        float(row.amount)
        for row in peers
        if extract_merchant(row.description, row.normalized_description) == merchant
    ]

    report = score_transaction(
        float(transaction.amount), peer_amounts, merchant_amounts
    )

    amount = float(transaction.amount)
    baseline = report["baseline"]
    ratio = report["ratio"]

    # The same threshold detect_anomalies() uses, so the drawer and the Unusual
    # page can never disagree about whether a row is flagged.
    from statistics import mean, pstdev

    spread = pstdev(peer_amounts)
    threshold = (
        mean(peer_amounts) + SIGMA * spread if spread > 0 else mean(peer_amounts) * 1.5
    )

    detail["is_anomaly"] = amount > threshold
    detail["anomaly"] = {
        "available": True,
        "score": report["score"],
        "factors": report["factors"],
        "baseline": baseline,
        "ratio": ratio,
        "peer_count": len(peer_amounts),
        "lookback_days": LOOKBACK_DAYS,
        "threshold": round(threshold, 2),
        "explanation": (
            f"Rs {_format_inr(amount)} is about {ratio:.1f}x your usual "
            f"{transaction.category} transaction of Rs {_format_inr(baseline)}, "
            f"measured across {len(peer_amounts)} transactions in the last "
            f"{LOOKBACK_DAYS} days."
            if detail["is_anomaly"]
            else (
                f"Rs {_format_inr(amount)} is in line with your usual "
                f"{transaction.category} spending of about "
                f"Rs {_format_inr(baseline)}."
            )
        ),
    }

    return detail
