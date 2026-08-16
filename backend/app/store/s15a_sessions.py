"""Signed-in sessions: issuing, resolving and ending them.

Before this existed, signing in was cosmetic — the browser remembered an
account and no endpoint ever asked who was calling, so anyone who could reach
the port could read every transaction. This is the piece that makes the gate
real.

Design, and why:

  - **The token is random, not derived.** 32 bytes from `secrets.token_urlsafe`.
    Nothing about the user is encoded in it, so nothing can be read out of it
    or forged by guessing how it was built.
  - **Only its hash is stored.** SHA-256 is enough here, unlike for passwords:
    a 256-bit random token has no low-entropy space to brute-force, which is
    exactly what the 600,000 PBKDF2 rounds on a password defend against.
  - **Sessions expire.** A session that outlives its expiry is a password that
    never changes.

No new dependency: `secrets` and `hashlib` are standard library. A JWT would
need one, and would also mean a token that stays valid after sign-out unless a
revocation list is kept — which is this table, with extra steps.
"""

import datetime as dt
import hashlib
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.core.s04_models import Session as SessionRow
from app.core.s04_models import User

TOKEN_BYTES = 32

# Long enough not to interrupt an evening of use, short enough that a token
# left on a shared machine stops working.
SESSION_DAYS = 14


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue(session: DbSession, user: User, now=None) -> str:
    """Create a session for a user and return the token to give the browser.

    The plain token is returned once, here, and never stored or logged. If it
    is lost, the user signs in again — which is the correct outcome.
    """
    now = now or dt.datetime.now()
    token = secrets.token_urlsafe(TOKEN_BYTES)

    session.add(
        SessionRow(
            token_hash=_hash_token(token),
            user_id=user.id,
            expires_at=now + dt.timedelta(days=SESSION_DAYS),
        )
    )
    session.commit()
    return token


def resolve(session: DbSession, token: str, now=None):
    """The user a token belongs to, or None.

    Returns None for absent, unknown and expired alike — the caller turns all
    three into the same 401, because telling them apart tells an attacker which
    tokens once existed.
    """
    if not token:
        return None

    now = now or dt.datetime.now()

    row = session.execute(
        select(SessionRow).where(SessionRow.token_hash == _hash_token(token))
    ).scalars().first()

    if row is None or row.expires_at <= now:
        return None

    return session.get(User, row.user_id)


def end(session: DbSession, token: str) -> bool:
    """Delete one session. True if a session was actually ended."""
    if not token:
        return False

    result = session.execute(
        delete(SessionRow).where(SessionRow.token_hash == _hash_token(token))
    )
    session.commit()
    return result.rowcount > 0


def end_all(session: DbSession, user_id: int) -> int:
    """Sign a user out everywhere. Used when a password changes."""
    result = session.execute(
        delete(SessionRow).where(SessionRow.user_id == user_id)
    )
    session.commit()
    return result.rowcount


def purge_expired(session: DbSession, now=None) -> int:
    """Drop sessions that have lapsed.

    Expired rows are already refused by `resolve`, so this is housekeeping
    rather than a security control — it stops the table growing forever.
    """
    now = now or dt.datetime.now()
    result = session.execute(
        delete(SessionRow).where(SessionRow.expires_at <= now)
    )
    session.commit()
    return result.rowcount
