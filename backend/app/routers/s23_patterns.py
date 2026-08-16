"""Duplicates, recurring payments and insights — the Phase 2 endpoints.

Grouped in one router because all three answer the same kind of question: what
shape does this set of transactions have, beyond the individual rows? None of
them stores its result; each is recomputed from the current data, for the same
reason anomalies are.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.pipeline.s10d_insights import build_insights
from app.s16_schemas import (
    DuplicatePair,
    DuplicateVerdictRequest,
    Insight,
    RecurringSummary,
)
from app.store import s12_aggregations as aggregations
from app.store.s14_anomaly_service import find_anomalies
from app.store.s15c_settings import sensitivity_for
from app.store.s14b_patterns import (
    duplicate_pairs,
    record_verdict,
    recurring_payments,
)

router = APIRouter(prefix="/api", tags=["patterns"])


@router.get("/duplicates", response_model=list[DuplicatePair])
def get_duplicates(
    include_decided: bool = Query(
        False, description="also return pairs the user has already ruled on"
    ),
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Pairs that look like one payment recorded twice, strongest first.

    Exact duplicates never reach the database — the fingerprint drops those at
    import. These are the near-misses: same amount and merchant a day or two
    apart, which is what a delayed card settlement looks like.
    """
    return duplicate_pairs(
        session,
        include_decided=include_decided,
        upload_id=upload_id,
        sheet=sheet,
        user_id=user.id,
        account_id=account_id,
        entry_source=entry_source,
    )


@router.post("/duplicates/verdict", status_code=204)
def set_duplicate_verdict(
    body: DuplicateVerdictRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Record what the user decided about a pair.

    Deliberately does not delete anything. Two identical payments on one day
    are often genuinely two payments, and only the person who made them knows
    — so this stores the answer and removes the pair from the queue.
    """
    verdict = record_verdict(
        session, body.first_id, body.second_id, body.is_duplicate, user_id=user.id
    )
    if verdict is None:
        raise HTTPException(
            status_code=404,
            detail="One or both transactions in that pair no longer exist.",
        )
    return None


@router.get("/recurring", response_model=RecurringSummary)
def get_recurring(
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Merchants being paid on a regular rhythm.

    Regularity of the gaps decides this, not how often a merchant appears —
    three trips to the same restaurant are not a subscription.
    """
    return recurring_payments(session, upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)


@router.get("/insights", response_model=list[Insight])
def get_insights(
    month: str | None = Query(None, description="YYYY-MM; omit for all time"),
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Observations drawn from figures that were already computed.

    Nothing here is generated text in the language-model sense — each sentence
    is a template filled from one arithmetic result, and each carries the
    comparison it came from.
    """
    source = {"upload_id": upload_id, "sheet": sheet, "user_id": user.id,
              "account_id": account_id,
              "entry_source": entry_source}

    summary = aggregations.summary(session, month, **source)
    trends = aggregations.monthly_trends(session, **source)
    anomalies = find_anomalies(
        session, sensitivity=sensitivity_for(session, user.id), **source
    )
    recurring = recurring_payments(session, **source)["payments"]

    return build_insights(summary, trends, anomalies, recurring)
