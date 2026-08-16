"""Sign up, sign in, sign out — email and password.

These endpoints create and check real accounts, and the token they hand back
is what every other route now demands. That is a change from how this started:
sign-in used to be cosmetic, and anyone who could reach the port could read
every transaction without it.

The token is returned in the response body, once. See store/s15a_sessions.py
for why only its hash is kept.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import _token_from_header, current_user
from app.s16_schemas import AccountOut, SignInRequest, SignUpRequest
from app.store import s15_accounts as accounts
from app.store import s15a_sessions as sessions

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/sign-up", response_model=AccountOut, status_code=201)
def sign_up(body: SignUpRequest, session: Session = Depends(get_session)):
    """Create an account, and treat the new account as signed in.

    409 rather than 400 for a taken address: it is a conflict with existing
    state, and the frontend uses the distinct status to offer "sign in
    instead" rather than just reprinting the message.
    """
    try:
        user = accounts.create_account(
            session, email=body.email, password=body.password, name=body.name
        )
    except accounts.EmailTaken as error:
        raise HTTPException(status_code=409, detail=str(error))
    except (accounts.InvalidEmail, accounts.WeakPassword) as error:
        raise HTTPException(status_code=422, detail=str(error))

    # A new account is signed in immediately; making someone type the password
    # they just chose teaches them nothing and loses the session they expect.
    return _with_token(session, user)


@router.post("/sign-in", response_model=AccountOut)
def sign_in(body: SignInRequest, session: Session = Depends(get_session)):
    """Check an email and password.

    401 is the same for an unknown address and a wrong password, carrying the
    same message, because distinguishing them would publish who has an
    account here.
    """
    try:
        user = accounts.authenticate(
            session, email=body.email, password=body.password
        )
    except accounts.AccountLocked as error:
        # 429 with Retry-After lets the screen count down rather than guess.
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after)},
        )
    except accounts.BadCredentials as error:
        raise HTTPException(status_code=401, detail=str(error))
    except accounts.InvalidEmail as error:
        raise HTTPException(status_code=422, detail=str(error))

    return _with_token(session, user)


@router.post("/sign-out", status_code=204)
def sign_out(
    authorization: str | None = Header(None),
    session: Session = Depends(get_session),
):
    """End the session for real.

    This used to be a no-op with a comment admitting it: there was no server
    session to end, so a "signed out" browser could still read everything. Now
    it deletes the row, and the token in the caller's hands stops working
    immediately.

    Deliberately never fails. A sign-out that errors leaves someone stuck
    signed in, which is the one outcome worse than a redundant call.
    """
    token = _token_from_header(authorization)
    if token:
        sessions.end(session, token)
    return None


@router.get("/me", response_model=AccountOut)
def me(user: User = Depends(current_user)):
    """Who the caller is. 401 when the token is missing, unknown or expired.

    The frontend calls this on load to find out whether a stored token is
    still good, rather than trusting what it remembers about itself.
    """
    return user


def _with_token(session: Session, user: User) -> AccountOut:
    """Issue a session and return the account with its token attached."""
    token = sessions.issue(session, user)
    return AccountOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        token=token,
    )
