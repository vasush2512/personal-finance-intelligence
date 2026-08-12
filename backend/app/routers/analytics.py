"""GET /api/summary and GET /api/trends — the dashboard's numbers."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import Summary, TrendPoint, UploadSource
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
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
    sheet: str | None = Query(
        None, description="worksheet name; empty string means rows with no sheet"
    ),
    session: Session = Depends(get_session),
):
    """Totals, the category split, and the biggest merchants."""
    return aggregations.summary(
        session, validated_month(month), upload_id=upload_id, sheet=sheet
    )


@router.get("/sources", response_model=list[UploadSource])
def get_sources(session: Session = Depends(get_session)):
    """The files and worksheets that transactions actually came from.

    The source filter is built from this, so its options are whatever is in
    the database — a workbook's tabs appear as tabs, and nothing is listed
    that has no rows behind it.
    """
    return aggregations.sources(session)


@router.get("/trends", response_model=list[TrendPoint])
def get_trends(
    upload_id: int | None = Query(None, description="restrict to one uploaded file"),
    sheet: str | None = Query(
        None, description="worksheet name; empty string means rows with no sheet"
    ),
    session: Session = Depends(get_session),
):
    """Spend and income per month, oldest first.

    Never narrowed by the month filter — the chart is what you pick a month
    from, so filtering it by that month would leave a single bar.
    """
    return aggregations.monthly_trends(session, upload_id=upload_id, sheet=sheet)
