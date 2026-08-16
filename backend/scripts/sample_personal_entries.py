"""Add a handful of manual entries so the Personal Expenses page has something
in it, and remove them again on request.

Run because the user asked for it. Nothing in the application creates these on
its own — this is a script you run deliberately, not seed data the app ships
with, and every row it writes is a real transaction in the real table exactly
as if it had been typed into the form.

Every entry is tagged `sample` so it can be found, filtered and removed. That
tag is the whole undo mechanism:

    python scripts/sample_personal_entries.py           # add them
    python scripts/sample_personal_entries.py --undo    # remove them again

`--undo` deletes only rows carrying that tag and only ones this script could
have made. It will not touch a statement row, and it will not touch a manual
row you typed yourself.
"""

import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.s01_constants import ENTRY_MANUAL  # noqa: E402
from app.core.s03_db import SessionLocal, create_all  # noqa: E402
from app.core.s04_models import Tag, Transaction, TransactionTag, User  # noqa: E402
from app.store.s11c_tags import set_tags, tags_for  # noqa: E402
from app.store.s11d_manual import create_manual, delete_manual  # noqa: E402

MARKER = "sample"

# (days ago, amount, direction, merchant, category, payment method, tags)
#
# Deliberately ordinary and deliberately varied: a couple of days with several
# small things, one large expense, one income, one uncategorised row so the
# suggestion behaviour is visible, and a few tags so the tag filter has
# something to filter.
ENTRIES = [
    (0, "40", "expense", "Chai Point", "food", "Cash", ["morning"]),
    (0, "180", "expense", "Metro", "transport", "UPI", []),
    (0, "260", "expense", "Blinkit", None, "UPI", []),
    (1, "1250", "expense", "Myntra", "shopping", "Card", []),
    (1, "450", "expense", "PVR Cinemas", "entertainment", "UPI", ["friends"]),
    (1, "90", "expense", "Chai Point", "food", "Cash", ["morning"]),
    (2, "2400", "expense", "Indian Oil", "transport", "Card", ["bike"]),
    (3, "620", "expense", "Apollo Pharmacy", "health", "UPI", []),
    (4, "8500", "expense", "Croma", "shopping", "Credit Card", []),
    (5, "310", "expense", "Swiggy", None, "UPI", ["friends"]),
    (6, "1000", "expense", "Cult Fit", "health", "UPI", []),
    (7, "70", "expense", "Auto", "transport", "Cash", []),
    (8, "4500", "expense", "Electricity Board", "bills_utilities", "Net banking", []),
    (2, "3000", "income", "Freelance project", "income", "UPI", ["work"]),
    (9, "82000", "income", "Techcadd Solutions", "income", "Net banking", []),
]


def add(session, user, today):
    made = []
    for days_ago, amount, direction, merchant, category, method, tags in ENTRIES:
        row = create_manual(
            session, user.id,
            amount=amount,
            date=today - dt.timedelta(days=days_ago),
            direction=direction,
            category=category,
            merchant=merchant,
            payment_method=method,
            today=today,
        )
        set_tags(session, user.id, row.id, [MARKER, *tags])
        made.append(row)

    spent = sum(float(row.amount) for row in made if row.direction == "debit")
    earned = sum(float(row.amount) for row in made if row.direction == "credit")

    print(f"\nAdded {len(made)} manual transactions for {user.email}")
    print(f"  spending  Rs {spent:,.0f}")
    print(f"  income    Rs {earned:,.0f}")
    print(f"\nEvery one is tagged '{MARKER}'.")
    print("Remove them any time with:")
    print("  python scripts/sample_personal_entries.py --undo")


def undo(session, user):
    tag = session.execute(
        select(Tag).where(Tag.user_id == user.id, Tag.name == MARKER)
    ).scalar_one_or_none()

    if tag is None:
        print("\nNothing to undo — no entries carry that tag.")
        return

    ids = session.execute(
        select(TransactionTag.transaction_id).where(TransactionTag.tag_id == tag.id)
    ).scalars().all()

    removed = 0
    for transaction_id in ids:
        row = session.get(Transaction, transaction_id)
        # Belt and braces: only manual rows, only this user's. delete_manual
        # refuses anything else anyway, but the guard says so out loud.
        if row is not None and row.entry_source == ENTRY_MANUAL:
            if delete_manual(session, user.id, transaction_id) is not None:
                removed += 1

    session.delete(tag)
    session.commit()
    print(f"\nRemoved {removed} sample transactions and the '{MARKER}' tag.")
    print("Nothing else was touched.")


def main(undoing: bool) -> int:
    create_all()
    session = SessionLocal()
    try:
        user = session.execute(select(User).order_by(User.id)).scalars().first()
        if user is None:
            print("No account exists yet. Sign up first.")
            return 1

        if undoing:
            undo(session, user)
        else:
            add(session, user, dt.date.today())
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main("--undo" in sys.argv))
