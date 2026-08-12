"""GET /api/anomalies — unusually large spending."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import Anomaly
from app.services.anomaly_service import find_anomalies

router = APIRouter(prefix="/api", tags=["anomalies"])


@router.get("/anomalies", response_model=list[Anomaly])
def get_anomalies(
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
    sheet: str | None = Query(
        None, description="worksheet name; empty string means rows with no sheet"
    ),
    session: Session = Depends(get_session),
):
    """Debits far above the usual for their category, newest first.

    Computed on every request, not stored — see anomaly_service.py.
    """
    return find_anomalies(session, upload_id=upload_id, sheet=sheet)
