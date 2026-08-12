"""GET /api/summary and GET /api/trends — the dashboard's numbers."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import Summary, TrendPoint
from app.services import aggregations

router = APIRouter(prefix="/api", tags=["analytics"])


def validated_month(month):
    """Reject a malformed month here rather than deep inside the SQL."""
    if month is None:
        return None
    try:
        aggregations.month_range(month)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"month must look like YYYY-MM, got {month!r}."
        )
    return month


@router.get("/summary", response_model=Summary)
def get_summary(
    month: str | None = Query(None, description="YYYY-MM; omit for all time"),
    session: Session = Depends(get_session),
):
    """Totals, the category split, and the biggest merchants."""
    return aggregations.summary(session, validated_month(month))


@router.get("/trends", response_model=list[TrendPoint])
def get_trends(session: Session = Depends(get_session)):
    """Spend and income per month, oldest first. Always the full history."""
    return aggregations.monthly_trends(session)
