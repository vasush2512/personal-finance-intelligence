"""Database side of the cash flow projection.

The arithmetic is in app/pipeline/s10e_forecast.py and knows nothing about
SQLAlchemy. This feeds it the monthly series and the recurring commitment, and
adds the one thing only the database can answer: how the month in progress is
tracking so far.
"""

import datetime as dt

from app.pipeline.s10e_forecast import forecast, month_progress
from app.store import s12_aggregations as aggregations
from app.store.s14b_patterns import recurring_payments


def cash_flow(session, today=None, **source):
    """The projection, its basis, and progress against it.

    `available` is false when there are too few complete months. The UI shows
    `reason` in that case rather than a figure — a projection from two months
    is a straight line drawn through two points and called a trend.
    """
    today = today or dt.date.today()

    trends = aggregations.monthly_trends(session, **source)

    # Recurring detection is the expensive part of this call, so it is only
    # worth running when there is going to be a projection to attach it to.
    committed = None
    if len(trends) >= 2:
        committed = recurring_payments(session, **source)["monthly_total"]

    result = forecast(trends, today=today, committed=committed)

    if result["available"]:
        result["progress"] = month_progress(
            trends, result["month"], result["projected_spending"], today=today
        )
    else:
        result["progress"] = None

    return result
