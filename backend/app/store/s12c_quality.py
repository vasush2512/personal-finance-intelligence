"""What is wrong, missing or odd about the imported data (Phase 4).

Every other figure in this app is only as good as the rows underneath it, and
several of the odder numbers on the dashboard turn out to be data problems
wearing an analysis costume: spending that reads as zero because a file had no
debit/credit column, a category that dominates because nothing recognised half
the merchants, a projection built on a month the statements only half cover.

So this collects those problems in one place and names them, instead of leaving
each one to be rediscovered on the page it happens to distort.

Two rules:

  - **A check reports; it does not repair.** Only one issue here has a fix
    safe enough to offer, and even that one runs from an explicit button, not
    on load. Quietly rewriting somebody's rows to make a dashboard look
    healthier is the opposite of a data quality tool.
  - **Every check honours the active filter.** Selecting one statement and
    then reading a data quality report about all of them is worse than no
    report: the counts describe a set of rows the rest of the screen is not
    showing.
  - **A clean check still appears**, with a count of zero. A list that only
    shows problems cannot tell you the difference between "checked, fine" and
    "never checked".
"""

import datetime as dt

from sqlalchemy import distinct, func, select, update

from app.core.s01_constants import SOURCE_NONE, SOURCE_RULE, UNCATEGORIZED
from app.core.s04_models import Transaction, Upload
from app.store.s12_aggregations import source_conditions

# Below this many rows an all-one-direction file is unremarkable — a short
# statement genuinely can be all debits.
_DIRECTION_SAMPLE = 20

# A gap of one month is a normal statement boundary. Two or more means
# something is actually missing.
_MAX_NORMAL_GAP = 1

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


def _issue(key, severity, title, count, detail, note=None, fix=None):
    """One finding, in the shape the UI renders."""
    return {
        "key": key,
        "severity": severity,
        "title": title,
        "count": count,
        "detail": detail,
        "note": note,
        # The label for the button, or None when there is nothing safe to do
        # automatically. Most of these are for a person to decide about.
        "fix_label": fix,
    }


def _stale_rule_rows(session, **source):
    """Rows stored as 'rule' that no rule can have produced.

    No keyword rule targets the fallback category, so this pairing is decisive.
    These date from before the source vocabulary distinguished "nothing
    matched" from "a rule matched", and they are why rule coverage read as
    100% while fifty thousand rows sat uncategorised.
    """
    count = session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.category_source == SOURCE_RULE,
            Transaction.category == UNCATEGORIZED,
            *source_conditions(**source),
        )
    ).scalar_one()

    return _issue(
        key="stale_rule_source",
        severity=SEVERITY_MEDIUM if count else SEVERITY_LOW,
        title="Rows labelled 'rule' that no rule matched",
        count=count,
        detail=(
            f"{count:,} rows say a keyword rule labelled them, but they sit in "
            f"the fallback category and no rule produces that. They are already "
            f"counted correctly on the Model page; this only changes what the "
            f"column itself says."
            if count
            else "Every row that claims a rule matched one."
        ),
        note=(
            "Safe to correct: it sets category_source to 'none' and touches "
            "nothing else — not the category, not the amount, not the date."
            if count
            else None
        ),
        fix="Correct the label" if count else None,
    )


def _uncategorized(session, **source):
    count = session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.category == UNCATEGORIZED, *source_conditions(**source)
        )
    ).scalar_one()
    total = session.execute(
        select(func.count(Transaction.id)).where(*source_conditions(**source))
    ).scalar_one() or 1
    share = round(count / total * 100, 1)

    return _issue(
        key="uncategorized",
        severity=(
            SEVERITY_HIGH if share > 40 else
            SEVERITY_MEDIUM if share > 15 else SEVERITY_LOW
        ),
        title="Transactions nothing could categorise",
        count=count,
        detail=(
            f"{count:,} rows ({share}% of everything) are still in the fallback "
            f"category. They are counted in your totals but not in any category "
            f"breakdown, which is why category shares can look smaller than "
            f"expected."
            if count
            else "Every transaction carries a real category."
        ),
        note=(
            "Correct a few by hand and retrain — the classifier learns from "
            "your corrections, so the same merchants stop landing here."
            if count
            else None
        ),
    )


def _one_direction_uploads(session, **source):
    """Files where every row went the same way.

    A statement with a single unsigned Amount column and no type column imports
    as all-debit or all-credit, and the giveaway is exactly this. It is the
    reason a file can show total spending of zero while clearly containing
    spending.
    """
    rows = session.execute(
        select(
            Upload.id,
            Upload.filename,
            func.count(Transaction.id),
            func.count(distinct(Transaction.direction)),
            func.min(Transaction.direction),
        )
        .join(Transaction, Transaction.upload_id == Upload.id)
        .where(*source_conditions(**source))
        .group_by(Upload.id)
        .having(func.count(Transaction.id) >= _DIRECTION_SAMPLE)
        .having(func.count(distinct(Transaction.direction)) == 1)
    ).all()

    names = [f"{filename} ({count:,} rows, all {direction})"
             for _, filename, count, _, direction in rows]

    return _issue(
        key="single_direction",
        severity=SEVERITY_HIGH if rows else SEVERITY_LOW,
        title="Files where every transaction went the same way",
        count=len(rows),
        detail=(
            "These files have no column saying which rows are money out and "
            "which are money in, so every row was read the same way: "
            + "; ".join(names[:3])
            + ("…" if len(names) > 3 else "")
            + ". Totals from these files are not trustworthy."
            if rows
            else "Every file has both money in and money out."
        ),
        note=(
            "Re-export the statement with a Debit/Credit or Type column, or "
            "with withdrawals and deposits in separate columns, then upload it "
            "again."
            if rows
            else None
        ),
    )


def _future_dated(session, today, **source):
    count = session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.date > today, *source_conditions(**source)
        )
    ).scalar_one()

    return _issue(
        key="future_dated",
        severity=SEVERITY_MEDIUM if count else SEVERITY_LOW,
        title="Transactions dated in the future",
        count=count,
        detail=(
            f"{count:,} rows are dated after today. They are included in totals "
            f"but excluded from the forecast baseline, because a month that has "
            f"not happened cannot be a complete month."
            if count
            else "No transaction is dated after today."
        ),
        note=(
            "Usually a date format read the wrong way round, or test data. "
            "Check the statement's date column."
            if count
            else None
        ),
    )


def _zero_amounts(session, **source):
    count = session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.amount == 0, *source_conditions(**source)
        )
    ).scalar_one()

    return _issue(
        key="zero_amount",
        severity=SEVERITY_MEDIUM if count else SEVERITY_LOW,
        title="Transactions with no amount",
        count=count,
        detail=(
            f"{count:,} rows imported with an amount of zero. They add nothing "
            f"to any total but do count towards transaction numbers."
            if count
            else "Every transaction has an amount."
        ),
    )


def _skipped_rows(session, **source):
    rows = session.execute(
        select(Upload.filename, Upload.rows_skipped, Upload.rows_parsed)
        .where(
            Upload.rows_skipped > 0,
            *([Upload.user_id == source["user_id"]] if source.get("user_id") is not None else []),
            *([Upload.id == source["upload_id"]] if source.get("upload_id") is not None else []),
        )
        .order_by(Upload.rows_skipped.desc())
    ).all()

    total = sum(skipped for _, skipped, _ in rows)
    names = [f"{filename} ({skipped:,} of {parsed:,})" for filename, skipped, parsed in rows]

    return _issue(
        key="skipped_rows",
        severity=SEVERITY_LOW,
        title="Rows skipped during import",
        count=total,
        detail=(
            "Lines that could not be read as a transaction were skipped rather "
            "than imported wrong: " + "; ".join(names[:3])
            + ("…" if len(names) > 3 else "")
            + ". Statement headers, balance lines and blank rows are normal here."
            if rows
            else "Every parsed row imported cleanly."
        ),
    )


def _month_gaps(session, **source):
    """Months with no transactions between months that have them."""
    # Labelled, because an unlabelled DISTINCT expression cannot be read back
    # out of the row by position on every SQLAlchemy version.
    month_column = func.strftime("%Y-%m", Transaction.date).label("month")

    months = [
        row.month
        for row in session.execute(
            select(month_column)
            .where(*source_conditions(**source))
            .distinct()
            .order_by(month_column)
        ).all()
        if row.month
    ]

    gaps = []
    for earlier, later in zip(months, months[1:]):
        distance = _months_between(earlier, later)
        if distance > _MAX_NORMAL_GAP:
            gaps.append(f"{earlier} → {later}")

    return _issue(
        key="month_gaps",
        severity=SEVERITY_MEDIUM if gaps else SEVERITY_LOW,
        title="Months with no transactions",
        count=len(gaps),
        detail=(
            "There are gaps in the record: " + ", ".join(gaps[:4])
            + ("…" if len(gaps) > 4 else "")
            + ". Trends and averages across a gap describe fewer months than "
            "they appear to."
            if gaps
            else "The months covered run continuously."
        ),
        note="Upload the missing statements to close the gaps." if gaps else None,
    )


def _months_between(earlier, later):
    early_year, early_month = (int(part) for part in earlier.split("-"))
    late_year, late_month = (int(part) for part in later.split("-"))
    return (late_year - early_year) * 12 + (late_month - early_month)


def data_quality(session, today=None, **source):
    """Every check, worst first, with a headline count of real problems."""
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

    total_rows = session.execute(
        select(func.count(Transaction.id)).where(*source_conditions(**source))
    ).scalar_one()
    flagged = [issue for issue in issues if issue["count"] > 0]

    return {
        "total_transactions": total_rows,
        "checks_run": len(issues),
        "issues_found": len(flagged),
        "issues": issues,
    }


def apply_fix(session, key, **source):
    """Run the one repair that is safe to automate. Returns rows changed.

    Raises KeyError for anything else, deliberately: every other issue on this
    page needs a human decision or a re-upload, and an endpoint that silently
    accepted an unknown key would be a promise it does not keep.
    """
    if key != "stale_rule_source":
        raise KeyError(key)

    result = session.execute(
        update(Transaction)
        .where(
            Transaction.category_source == SOURCE_RULE,
            Transaction.category == UNCATEGORIZED,
            *source_conditions(**source),
        )
        .values(category_source=SOURCE_NONE)
    )
    session.commit()
    return result.rowcount
