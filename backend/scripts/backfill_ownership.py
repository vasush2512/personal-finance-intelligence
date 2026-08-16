"""Assign existing transactions and uploads to their owner. Run once.

Ownership arrived after the data did. Every row imported before that has
user_id NULL, and since every query now filters on it, those rows are invisible
until this runs — the app would show a correct, complete, and entirely empty
dashboard.

Deliberately a script rather than a startup hook. Assigning ownership of
somebody's financial records is not a thing to do silently as a side effect of
a server restart, and it only ever needs to happen once.

Refuses to guess: with more than one account it stops and asks, because there
is no safe way to work out from the data which user 105,000 rows belong to.

    python scripts/backfill_ownership.py            # report only
    python scripts/backfill_ownership.py --apply    # actually write
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, update  # noqa: E402

from app.core.s03_db import SessionLocal, create_all  # noqa: E402
from app.core.s04_models import Transaction, Upload, User  # noqa: E402


def main(apply: bool) -> int:
    # The project's own migration step: adds any missing nullable column,
    # including the user_id this script is about to fill in. Normally the
    # server does this at startup; running it here means the backfill works
    # whether or not the app has been started since the upgrade.
    create_all()

    session = SessionLocal()
    try:
        users = session.execute(select(User).order_by(User.id)).scalars().all()

        orphan_txns = session.execute(
            select(func.count(Transaction.id)).where(Transaction.user_id.is_(None))
        ).scalar_one()
        orphan_uploads = session.execute(
            select(func.count(Upload.id)).where(Upload.user_id.is_(None))
        ).scalar_one()

        print(f"accounts:            {len(users)}")
        print(f"unowned transactions {orphan_txns:,}")
        print(f"unowned uploads      {orphan_uploads:,}")

        if orphan_txns == 0 and orphan_uploads == 0:
            print("\nNothing to do — every row already has an owner.")
            return 0

        if not users:
            print("\nNo accounts exist. Sign up first, then run this again.")
            return 1

        if len(users) > 1:
            print("\nMore than one account exists, and nothing in the data says "
                  "which of them these rows belong to. Refusing to guess.")
            for user in users:
                print(f"  id={user.id}  {user.email}")
            print("\nAssign them deliberately, or delete the rows and re-upload "
                  "the statements from the account that should own them.")
            return 1

        owner = users[0]
        print(f"\nowner:               id={owner.id}  {owner.email}")

        if not apply:
            print("\nDry run. Re-run with --apply to write these changes.")
            return 0

        changed_txns = session.execute(
            update(Transaction)
            .where(Transaction.user_id.is_(None))
            .values(user_id=owner.id)
        ).rowcount
        changed_uploads = session.execute(
            update(Upload).where(Upload.user_id.is_(None)).values(user_id=owner.id)
        ).rowcount
        session.commit()

        print(f"\nassigned {changed_txns:,} transactions and "
              f"{changed_uploads:,} uploads to {owner.email}.")
        print("Nothing else was modified — not a category, an amount or a date.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main("--apply" in sys.argv))
