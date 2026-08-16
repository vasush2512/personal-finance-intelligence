"""Forecast, model statistics, corrections and the monthly story — Phase 3.

Grouped in one router because all four answer questions about the system
rather than about a transaction: what is likely next month, what is labelling
the data, what has been corrected, and what a month amounted to.

None of it stores a result. Every figure is recomputed from the current data,
for the same reason anomalies and duplicates are: a stored answer goes stale
the moment a new statement arrives, and nothing would recompute it.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.pipeline.s10f_story import build_story
from app.s16_schemas import (
    CashFlowForecast,
    Correction,
    ModelStats,
    MonthlyStory,
)
from app.store import s12_aggregations as aggregations
from app.store.s12b_forecast import cash_flow
from app.store.s13a_model_stats import model_stats
from app.store.s14_anomaly_service import find_anomalies
from app.store.s15c_settings import sensitivity_for
from app.store.s14b_patterns import recurring_payments
from app.store.s14c_feedback import RECENT_LIMIT, recent_corrections

router = APIRouter(prefix="/api", tags=["intelligence"])


def _valid_month(month: str) -> str:
    """Reject a malformed month here rather than let it reach a query."""
    try:
        dt.datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"month must look like YYYY-MM, got {month!r}."
        )
    return month


@router.get("/forecast", response_model=CashFlowForecast)
def get_forecast(
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
    """Next month's spending and income, projected from complete months.

    The month in progress is never part of the baseline — on the 3rd of the
    month it is almost entirely missing, and averaging it in would drag every
    projection down.
    """
    return cash_flow(session, upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)


@router.get("/model/stats", response_model=ModelStats)
def get_model_stats(
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
    """What is labelling the data, and how sure it is.

    There is no single accuracy figure here on purpose. The classifier is
    trained on labels the keyword rules produced, so agreement with them says
    it learned to imitate the rules — not that either is correct.
    """
    return model_stats(session, upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)


@router.get("/feedback", response_model=list[Correction])
def get_feedback(
    limit: int = Query(RECENT_LIMIT, ge=1, le=100),
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(None),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Category corrections the user has made, newest first."""
    return recent_corrections(
        session, limit=limit, user_id=user.id, upload_id=upload_id,
        sheet=sheet, account_id=account_id,
        entry_source=entry_source,
    )


@router.get("/story", response_model=MonthlyStory)
def get_story(
    month: str | None = Query(None, description="YYYY-MM; omit for the latest month"),
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
    """One month written as paragraphs rather than boxes.

    Every sentence is a template filled from a figure computed elsewhere. There
    is no advice in it, and nothing is estimated.
    """
    source = {"upload_id": upload_id, "sheet": sheet, "user_id": user.id,
              "account_id": account_id,
              "entry_source": entry_source}
    trends = aggregations.monthly_trends(session, **source)

    if month:
        _valid_month(month)
    elif trends:
        month = trends[-1]["month"]
    else:
        return MonthlyStory(
            available=False,
            month="",
            title="No data",
            reason="There are no transactions to write about yet.",
        )

    # The month before this one, for the comparison paragraph. Absent for the
    # first month in the data, and the paragraph is then simply not written.
    index = next(
        (i for i, point in enumerate(trends) if point["month"] == month), None
    )
    previous = trends[index - 1] if index else None

    return build_story(
        month,
        aggregations.summary(session, month, **source),
        previous=previous,
        anomalies=[
            row for row in find_anomalies(
        session, sensitivity=sensitivity_for(session, user.id), **source
    )
            if str(row["date"]).startswith(month)
        ],
        recurring=recurring_payments(session, **source)["payments"],
    )
