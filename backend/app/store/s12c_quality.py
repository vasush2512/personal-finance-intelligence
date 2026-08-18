"""What is wrong, missing or odd about the imported data (Phase 4).

Every other figure in this app is only as good as the rows underneath it, and
several of the odder numbers on the dashboard turn out to be data problems
wearing an analysis costume: spending that reads as zero because a file had no
debit/credit column, a category that dominates because nothing recognised half
the merchants. This collects those problems in one place and names them.
"""

import datetime as dt

from sqlalchemy import distinct, func, select, update

from app.core.s01_constants import SOURCE_NONE, SOURCE_RULE, UNCATEGORIZED
from app.core.s04_models import Transaction, Upload
from app.store.s12_aggregations import source_conditions

_DIRECTION_SAMPLE = 20
_MAX_NORMAL_GAP = 1
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


def _issue(key, severity, title, count, detail, note=None, fix=None):
    return {"key": key, "severity": severity, "title": title, "count": count,
            "detail": detail, "note": note, "fix_label": fix}


def _stale_rule_rows(session, **source):
    count = session.execute(select(func.count(Transaction.id)).where(
        Transaction.category_source == SOURCE_RULE,
        Transaction.category == UNCATEGORIZED,
        *source_conditions(**source),
    )).scalar_one()
    return _issue(
        "stale_rule_source", SEVERITY_MEDIUM if count else SEVERITY_LOW,
        "Rows labelled 'rule' that no rule matched", count,
        (f"{count:,} rows say a keyword rule labelled them, but they sit in the fallback category and no rule produces that. They are already counted correctly on the Model page; this only changes what the column itself says."
         if count else "Every row that claims a rule matched one."),
        ("Safe to correct: it sets category_source to 'none' and touches nothing else — not the category, not the amount, not the date." if count else None),
        "Correct the label" if count else None,
    )


def _uncategorized(session, **source):
    count = session.execute(select(func.count(Transaction.id)).where(
        Transaction.category == UNCATEGORIZED, *source_conditions(**source)
    )).scalar_one()
    total = session.execute(select(func.count(Transaction.id)).where(*source_conditions(**source))).scalar_one() or 1
    share = round(count / total * 100, 1)
    return _issue(
        "uncategorized",
        SEVERITY_HIGH if share > 40 else SEVERITY_MEDIUM if share > 15 else SEVERITY_LOW,
        "Transactions nothing could categorise", count,
        (f"{count:,} rows ({share}% of everything) are still in the fallback category. They are counted in your totals but not in any category breakdown, which is why category shares can look smaller than expected."
         if count else "Every transaction carries a real category."),
        ("Correct a few by hand and retrain — the classifier learns from your corrections, so the same merchants stop landing here." if count else None),
    )


def _one_direction_uploads(session, **source):
    rows = session.execute(select(
        Upload.id, Upload.filename, func.count(Transaction.id),
        func.count(distinct(Transaction.direction)), func.min(Transaction.direction),
    ).join(Transaction, Transaction.upload_id == Upload.id).where(*source_conditions(**source))
      .group_by(Upload.id)
      .having(func.count(Transaction.id) >= _DIRECTION_SAMPLE)
      .having(func.count(distinct(Transaction.direction)) == 1)).all()
    names = [f"{filename} ({count:,} rows, all {direction})" for _, filename, count, _, direction in rows]
    return _issue(
        "single_direction", SEVERITY_HIGH if rows else SEVERITY_LOW,
        "Files where every transaction went the same way", len(rows),
        ("These files have no column saying which rows are money out and which are money in, so every row was read the same way: " + "; ".join(names[:3]) + ("…" if len(names) > 3 else "") + ". Totals from these files are not trustworthy."
         if rows else "Every file has both money in and money out."),
        ("Re-export the statement with a Debit/Credit or Type column, or with withdrawals and deposits in separate columns, then upload it again." if rows else None),
    )


def _future_dated(session, today, **source):
    count = session.execute(select(func.count(Transaction.id)).where(
        Transaction.date > today, *source_conditions(**source)
    )).scalar_one()
    return _issue(
        "future_dated", SEVERITY_MEDIUM if count else SEVERITY_LOW,
        "Transactions dated in the future", count,
        (f"{count:,} rows are dated after today. They are included in totals but excluded from the forecast baseline, because a month that has not happened cannot be a complete month."
         if count else "No transaction is dated after today."),
        ("Usually a date format read the wrong way round, or test data. Check the statement's date column." if count else None),
    )


def _zero_amounts(session, **source):
    count = session.execute(select(func.count(Transaction.id)).where(
        Transaction.amount == 0, *source_conditions(**source)
    )).scalar_one()
    return _issue(
        "zero_amount", SEVERITY_MEDIUM if count else SEVERITY_LOW,
        "Transactions with no amount", count,
        (f"{count:,} rows imported with an amount of zero. They add nothing to any total but do count towards transaction numbers." if count else "Every transaction has an amount."),
    )


def _skipped_rows(session, **source):
    rows = session.execute(select(Upload.filename, Upload.rows_skipped, Upload.rows_parsed).where(
        Upload.rows_skipped > 0,
        *([Upload.user_id == source["user_id"]] if source.get("user_id") is not None else []),
        *([Upload.id == source["upload_id"]] if source.get("upload_id") is not None else []),
    ).order_by(Upload.rows_skipped.desc())).all()
    total = sum(skipped for _, skipped, _ in rows)
    names = [f"{filename} ({skipped:,} of {parsed:,})" for filename, skipped, parsed in rows]
    return _issue(
        "skipped_rows", SEVERITY_LOW, "Rows skipped during import", total,
        ("Lines that could not be read as a transaction were skipped rather than imported wrong: " + "; ".join(names[:3]) + ("…" if len(names) > 3 else "") + ". Statement headers, balance lines and blank rows are normal here."
         if rows else "Every parsed row imported cleanly."),
    )


def _month_gaps(session, **source):
    """Find missing calendar months using Python, avoiding SQLite-only date functions."""
    dates = session.execute(select(Transaction.date).where(*source_conditions(**source))).scalars().all()
    months = sorted({(value.year, value.month) for value in dates if value is not None})

    gaps = []
    for earlier, later in zip(months, months[1:]):
        distance = (later[0] - earlier[0]) * 12 + (later[1] - earlier[1])
        if distance > _MAX_NORMAL_GAP:
            gaps.append(f"{earlier[0]:04d}-{earlier[1]:02d} → {later[0]:04d}-{later[1]:02d}")

    return _issue(
        "month_gaps", SEVERITY_MEDIUM if gaps else SEVERITY_LOW,
        "Months with no transactions", len(gaps),
        ("There are gaps in the record: " + ", ".join(gaps[:4]) + ("…" if len(gaps) > 4 else "") + ". Trends and averages across a gap describe fewer months than they appear to."
         if gaps else "The months covered run continuously."),
        "Upload the missing statements to close the gaps." if gaps else None,
    )


def data_quality(session, today=None, **source):
    today = today or dt.date.today()
    issues = [
        _one_direction_uploads(session, **source),
        _uncategorized(session, **source),
        _stale_rule_rows(session, **source),
        _future_dated(session, today, **source),
        _month_gaps(session, **source),
        _zero_amounts(session, **source),
        _skipped_rows(session, **source),
    ]
    order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    issues.sort(key=lambda issue: (order[issue["severity"]], -issue["count"]))
    total_rows = session.execute(select(func.count(Transaction.id)).where(*source_conditions(**source))).scalar_one()
    flagged = [issue for issue in issues if issue["count"] > 0]
    return {"total_transactions": total_rows, "checks_run": len(issues), "issues_found": len(flagged), "issues": issues}


def apply_fix(session, key, **source):
    if key != "stale_rule_source":
        raise KeyError(key)
    result = session.execute(update(Transaction).where(
        Transaction.category_source == SOURCE_RULE,
        Transaction.category == UNCATEGORIZED,
        *source_conditions(**source),
    ).values(category_source=SOURCE_NONE))
    session.commit()
    return result.rowcount
