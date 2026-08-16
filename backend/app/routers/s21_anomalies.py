"""GET /api/anomalies — unusually large spending."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import Anomaly
from app.store.s14_anomaly_service import find_anomalies
from app.store.s15c_settings import sensitivity_for

router = APIRouter(prefix="/api", tags=["anomalies"])


@router.get("/anomalies", response_model=list[Anomaly])
def get_anomalies(
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
    sheet: str | None = Query(
        None, description="worksheet name; empty string means rows with no sheet"
    ),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Debits far above the usual for their category, newest first.

    Computed on every request, not stored — see anomaly_service.py.
    """
    return find_anomalies(session, sensitivity=sensitivity_for(session, user.id),
        upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)
