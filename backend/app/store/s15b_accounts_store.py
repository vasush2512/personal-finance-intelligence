"""Bank accounts the user uploads statements for.

Small enough to be one file: accounts are a label and a foreign key, not a
domain. What makes them worth having is that every query in the app can now be
narrowed to one bank, which is the question people actually ask once a second
statement is loaded — "how much did I spend from the salary account?"
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.s04_models import Account, Transaction, Upload

MAX_ACCOUNTS = 30


class AccountError(ValueError):
    """An account that cannot be stored, with a message worth showing."""


def _clean_last4(value: str) -> str:
    """Keep four digits at most, and only digits.

    A full account number has no use anywhere in this app, so there is no
    reason to hold one — anything longer is trimmed to its last four rather
    than rejected, because pasting the whole number is the obvious mistake.
    """
    digits = "".join(character for character in (value or "") if character.isdigit())
    return digits[-4:]


def list_accounts(session: Session, user_id: int):
    """Every account, with how many transactions each currently holds."""
    counts = dict(
        session.execute(
            select(Transaction.account_id, func.count(Transaction.id))
            .where(Transaction.user_id == user_id)
            .group_by(Transaction.account_id)
        ).all()
    )

    rows = session.execute(
        select(Account).where(Account.user_id == user_id).order_by(Account.id)
    ).scalars().all()

    accounts = [
        {
            "id": row.id,
            "name": row.name,
            "bank": row.bank,
            "last4": row.last4,
            "kind": row.kind,
            "transaction_count": counts.get(row.id, 0),
        }
        for row in rows
    ]

    # Statements imported before accounts existed, and any uploaded without
    # choosing one. Surfaced rather than hidden: they are still in every total,
    # and a filter that cannot reach them would quietly disagree with the
    # dashboard.
    unassigned = counts.get(None, 0)
    if unassigned:
        accounts.append({
            "id": None,
            "name": "Unassigned",
            "bank": "",
            "last4": "",
            "kind": "unassigned",
            "transaction_count": unassigned,
        })

    return accounts


def create_account(session: Session, user_id: int, name: str, bank: str = "",
                   last4: str = "", kind: str = "savings"):
    name = (name or "").strip()
    if len(name) < 2:
        raise AccountError("Give the account a name you will recognise.")
    if len(name) > 60:
        raise AccountError("That name is too long.")

    existing = session.execute(
        select(func.count(Account.id)).where(Account.user_id == user_id)
    ).scalar_one()
    if existing >= MAX_ACCOUNTS:
        raise AccountError(f"That is more than {MAX_ACCOUNTS} accounts.")

    duplicate = session.execute(
        select(Account).where(Account.user_id == user_id, Account.name == name)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise AccountError(f"You already have an account called {name!r}.")

    account = Account(
        user_id=user_id,
        name=name,
        bank=(bank or "").strip()[:60],
        last4=_clean_last4(last4),
        kind=(kind or "savings").strip()[:20],
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def delete_account(session: Session, user_id: int, account_id: int):
    """Remove an account. Its transactions stay, and become unassigned.

    Deliberately not a cascade. Deleting a label should not delete a year of
    financial records, and someone renaming their accounts should not lose
    their data to a mis-click.
    """
    account = session.get(Account, account_id)
    if account is None or account.user_id != user_id:
        return None

    orphaned = session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.account_id == account_id
        )
    ).scalar_one()

    for row in session.execute(
        select(Transaction).where(Transaction.account_id == account_id)
    ).scalars():
        row.account_id = None

    for upload in session.execute(
        select(Upload).where(Upload.account_id == account_id)
    ).scalars():
        upload.account_id = None

    session.delete(account)
    session.commit()
    return {"name": account.name, "transactions_unassigned": orphaned}


def assign_upload(session: Session, user_id: int, upload_id: int, account_id):
    """Move an already-imported statement to an account.

    Updates the upload and every row that came from it, so the denormalised
    account_id on transactions cannot drift from the upload it belongs to.
    """
    upload = session.get(Upload, upload_id)
    if upload is None or upload.user_id != user_id:
        return None

    if account_id is not None:
        account = session.get(Account, account_id)
        if account is None or account.user_id != user_id:
            return None

    upload.account_id = account_id
    moved = 0
    for row in session.execute(
        select(Transaction).where(
            Transaction.upload_id == upload_id, Transaction.user_id == user_id
        )
    ).scalars():
        row.account_id = account_id
        moved += 1

    session.commit()
    return {"upload_id": upload_id, "account_id": account_id, "moved": moved}
