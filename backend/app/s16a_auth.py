"""The authentication dependency every data endpoint depends on.

One import, one line per route, and the route can no longer be called by
someone who is not signed in:

    def list_transactions(user: User = Depends(current_user)):

And one helper the queries use, so ownership is expressed the same way
everywhere rather than re-remembered per query:

    .where(*owned(user), *other_conditions)

Both live here — between the schemas and the routers — because they are part of
the HTTP boundary rather than of the data layer. `store/` stays callable from a
script or a test with no request in sight.
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import Transaction, User
from app.store.s15a_sessions import resolve

# One message for absent, malformed, unknown and expired tokens alike. Telling
# them apart tells an attacker which tokens once existed.
_UNAUTHORIZED = "Sign in to continue."


def _token_from_header(authorization: str | None) -> str | None:
    """Pull the token out of 'Authorization: Bearer <token>'."""
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None

    return token.strip()


def current_user(
    authorization: str | None = Header(None),
    session: Session = Depends(get_session),
) -> User:
    """The signed-in user, or 401.

    Every endpoint that touches financial data depends on this. An endpoint
    that forgets it is not a smaller vulnerability than one with a bug in it —
    it is the whole of the vulnerability — so the test suite checks the router
    table rather than trusting that nobody forgot.
    """
    user = resolve(session, _token_from_header(authorization))

    if user is None:
        raise HTTPException(
            status_code=401,
            detail=_UNAUTHORIZED,
            # Tells a browser client this is an auth failure rather than a
            # permissions one, so it can send the user to sign in.
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def optional_user(
    authorization: str | None = Header(None),
    session: Session = Depends(get_session),
) -> User | None:
    """The signed-in user if there is one, otherwise None.

    For the handful of endpoints that are legitimately public — the category
    vocabulary, liveness — where 401 would be wrong.
    """
    return resolve(session, _token_from_header(authorization))


def owned(user: User):
    """The ownership condition for a transaction query.

    Returned as a list so it composes with the other condition lists the
    aggregations already build:

        .where(*owned(user), *month_conditions(month))

    A query that forgets this returns another user's money. That is why it is
    one short call rather than something to hand-write per query.
    """
    return [Transaction.user_id == user.id]
