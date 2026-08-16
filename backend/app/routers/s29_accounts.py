"""Bank accounts, and which statement belongs to which."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import (
    AccountAssign,
    AccountCreate,
    AccountDeleted,
    AccountSummary,
)
from app.store.s15b_accounts_store import (
    AccountError,
    assign_upload,
    create_account,
    delete_account,
    list_accounts,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountSummary])
def get_accounts(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Every account with its transaction count.

    Statements uploaded before accounts existed appear as "Unassigned" with a
    null id — they are still in every total, and a filter that could not reach
    them would quietly disagree with the dashboard.
    """
    return list_accounts(session, user.id)


@router.post("", response_model=AccountSummary, status_code=201)
def post_account(
    body: AccountCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    try:
        account = create_account(
            session, user.id, body.name, body.bank, body.last4, body.kind
        )
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error))

    return AccountSummary(
        id=account.id, name=account.name, bank=account.bank,
        last4=account.last4, kind=account.kind, transaction_count=0,
    )


@router.post("/assign", response_model=AccountAssign)
def post_assign(
    body: AccountAssign,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Move an already-imported statement to an account."""
    result = assign_upload(session, user.id, body.upload_id, body.account_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No such statement or account.")
    return AccountAssign(**result)


@router.delete("/{account_id}", response_model=AccountDeleted)
def remove_account(
    account_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Delete an account. Its transactions stay, and become unassigned.

    Deliberately not a cascade: deleting a label should not delete a year of
    financial records.
    """
    result = delete_account(session, user.id, account_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No such account.")
    return AccountDeleted(account_id=account_id, **result)
