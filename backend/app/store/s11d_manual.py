"""Creating, editing and removing manually entered transactions.

A manual entry becomes an ordinary row in the ordinary transactions table.
Nothing downstream is told where it came from: the dashboard, the anomaly
detector, the forecast and the exports all pick it up because it is simply a
transaction. That is the entire integration, and it is why there is no
manual_analytics.py anywhere in this project.

What this module owns is the small set of rules that only apply to rows a
person typed:

  - **The user's choice outranks the categoriser.** If they picked a category
    it is stored as SOURCE_USER, and no rule or model may overwrite it later —
    the same protection a correction on an imported row already has.
  - **Only manual rows may be edited or deleted here.** A statement row's
    amount and date came from a bank; the app has no business rewriting them,
    and removing one is what deleting its upload is for.
  - **A suggestion is offered, never applied silently.** The categoriser runs
    when the user left the category blank, and what it produced is recorded as
    the rule/model's answer, not as theirs.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s01_constants import (
    ENTRY_MANUAL,
    SOURCE_NONE,
    SOURCE_RULE,
    SOURCE_USER,
    UNCATEGORIZED,
)
from app.core.s04_models import Account, Transaction
from app.pipeline.s08_rules import categorize_by_rules
from app.pipeline.s10h_manual import InvalidEntry, build_manual_transaction
from app.store.s11a_rules import active_pairs
from app.store.s11b_categories import CategoryError, ensure_valid


def suggest_category(session: Session, user_id: int, merchant: str, notes: str = ""):
    """What the existing categoriser makes of a typed merchant name.

    Reuses the same rules the import pipeline uses — the user's own rules
    first, then the built-in ones. Returns None when nothing matches, which is
    an honest answer and better than guessing at a category for "xyz".

    The model is deliberately not consulted here. It was trained on bank
    narrations, a typed merchant name is a different kind of string, and a
    confident-looking suggestion drawn from the wrong distribution is worse
    than no suggestion at all.
    """
    text = " ".join(part for part in (merchant, notes) if part).strip()
    if not text:
        return None

    from app.pipeline.s05_normalize import normalize_description

    category = categorize_by_rules(
        normalize_description(text), active_pairs(session, user_id)
    )
    if category is None or category == UNCATEGORIZED:
        return None

    return category


def create_manual(session: Session, user_id: int, *, amount, date, direction,
                  category=None, merchant="", payment_method="", notes="",
                  account_id=None, today=None):
    """Validate and store one manual transaction. Returns the row.

    Raises InvalidEntry or CategoryError with a message worth showing.
    """
    fields = build_manual_transaction(
        amount=amount, date=date, direction=direction, category=None,
        merchant=merchant, payment_method=payment_method, notes=notes,
        today=today,
    )

    # An account that is not this user's is refused rather than ignored: a
    # transaction filed under someone else's account is a data leak with extra
    # steps, and silently dropping the choice would leave the user thinking it
    # had been recorded.
    if account_id is not None:
        account = session.get(Account, account_id)
        if account is None or account.user_id != user_id:
            raise CategoryError("That account does not exist.")

    if category:
        ensure_valid(session, user_id, category)
        chosen, source = category, SOURCE_USER
    else:
        suggested = suggest_category(session, user_id, merchant, notes)
        chosen = suggested or UNCATEGORIZED
        source = SOURCE_RULE if suggested else SOURCE_NONE

    row = Transaction(
        user_id=user_id,
        account_id=account_id,
        upload_id=None,
        date=fields["date"],
        description=fields["description"],
        normalized_description=fields["normalized_description"],
        merchant_name=fields["merchant_name"],
        amount=fields["amount"],
        direction=fields["direction"],
        category=chosen,
        category_source=source,
        confidence=None,
        payment_method=fields["payment_method"],
        notes=fields["notes"],
        entry_source=ENTRY_MANUAL,
        fingerprint=fields["fingerprint"],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def is_manual(row: Transaction) -> bool:
    """NULL entry_source means it came from a statement — see constants."""
    return row.entry_source == ENTRY_MANUAL


def update_manual(session: Session, user_id: int, transaction_id: int, **changes):
    """Edit a manual transaction. Returns the row, or None when not allowed.

    Refuses on a statement row: its amount, date and description came from a
    bank, and an app that lets you rewrite them is no longer a record of what
    happened. Changing the *category* of a statement row is a different thing
    and already has its own endpoint.
    """
    row = session.get(Transaction, transaction_id)
    if row is None or row.user_id != user_id or not is_manual(row):
        return None

    # Rebuild through the same validator that created it, so an edit cannot
    # write a value the create path would have refused.
    rebuilt = build_manual_transaction(
        amount=changes.get("amount", row.amount),
        date=changes.get("date", row.date),
        direction=changes.get("direction", row.direction),
        merchant=changes.get("merchant", row.merchant_name or ""),
        payment_method=changes.get("payment_method", row.payment_method or ""),
        notes=changes.get("notes", row.notes or ""),
        today=changes.get("today"),
    )

    if changes.get("account_id", "unset") != "unset":
        account_id = changes["account_id"]
        if account_id is not None:
            account = session.get(Account, account_id)
            if account is None or account.user_id != user_id:
                raise CategoryError("That account does not exist.")
        row.account_id = account_id

    if changes.get("category"):
        ensure_valid(session, user_id, changes["category"])
        row.category = changes["category"]
        # An edit that names a category is the person deciding, which is the
        # strongest label this app records.
        row.category_source = SOURCE_USER
        row.confidence = None

    row.date = rebuilt["date"]
    row.description = rebuilt["description"]
    row.normalized_description = rebuilt["normalized_description"]
    row.merchant_name = rebuilt["merchant_name"]
    row.amount = rebuilt["amount"]
    row.direction = rebuilt["direction"]
    row.payment_method = rebuilt["payment_method"]
    row.notes = rebuilt["notes"]
    # The fingerprint is NOT regenerated. It identifies this row, and changing
    # it would make an already-recorded duplicate verdict point at nothing.
    row.updated_at = dt.datetime.now()

    session.commit()
    session.refresh(row)
    return row


def delete_manual(session: Session, user_id: int, transaction_id: int):
    """Remove a manual transaction. Returns what was deleted, or None.

    Only manual rows. A statement row is part of an imported file, and the
    established way to remove those is to delete the upload — which reports
    how many rows went with it. Allowing one-off deletion of imported rows
    would make an upload's count stop matching what is in the database.
    """
    row = session.get(Transaction, transaction_id)
    if row is None or row.user_id != user_id or not is_manual(row):
        return None

    summary = {
        "id": row.id,
        "amount": row.amount,
        "merchant": row.merchant,
        "date": row.date,
    }
    session.delete(row)
    session.commit()
    return summary


def manual_summary(session: Session, user_id: int, today=None, **source):
    """The figures the Personal Expenses page opens with.

    Computed from the same rows every other page reads. Returns `available`
    false when there is nothing yet, so the page can say "nothing recorded"
    rather than showing a confident ₹0 — the two mean different things.
    """
    from decimal import Decimal

    from app.store import s12_aggregations as aggregations

    today = today or dt.date.today()
    month = f"{today.year:04d}-{today.month:02d}"

    rows = session.execute(
        select(Transaction).where(
            Transaction.entry_source == ENTRY_MANUAL,
            *aggregations.source_conditions(user_id=user_id, **source),
        ).order_by(Transaction.date.desc(), Transaction.id.desc())
    ).scalars().all()

    if not rows:
        return {
            "available": False,
            "reason": "Nothing recorded by hand yet.",
            "total_count": 0,
        }

    debits = [row for row in rows if row.direction == "debit"]
    this_month = [row for row in debits if row.date.strftime("%Y-%m") == month]
    todays = [row for row in debits if row.date == today]

    days_covered = len({row.date for row in this_month}) or 1
    month_total = sum((row.amount for row in this_month), Decimal("0.00"))

    return {
        "available": True,
        "reason": None,
        "month": month,
        "today_total": sum((row.amount for row in todays), Decimal("0.00")),
        "month_total": month_total,
        "month_income": sum(
            (row.amount for row in rows
             if row.direction == "credit" and row.date.strftime("%Y-%m") == month),
            Decimal("0.00"),
        ),
        "average_daily": (month_total / days_covered).quantize(Decimal("0.01")),
        "largest": max((row.amount for row in debits), default=Decimal("0.00")),
        "total_count": len(rows),
        "month_count": len(this_month),
    }
