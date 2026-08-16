"""Email accounts: signing up, signing in, and storing a password safely.

Replaces the phone/OTP flow. An account is a real row in the database with a
real hashed password, so signing up and signing back in tomorrow works.

What this is honest about
-------------------------
The password handling here is done properly — see `hash_password` for why
each part is the way it is. What is NOT here is authorization: no other
endpoint asks who you are, so signing in unlocks the user interface and
nothing else. Anyone who can reach the API can read the transactions whether
they have an account or not.

That is a deliberate, stated limit rather than an oversight. Gating the API
means sessions, tokens and an owner column on every row, which is a different
piece of work. The login screen says so on itself instead of implying a
protection that is not there.

No new dependency: `hashlib.pbkdf2_hmac` is in the standard library, so this
needs neither bcrypt nor passlib.
"""

import base64
import datetime as dt
import hashlib
import hmac
import re
import secrets

from sqlalchemy import func, select

from app.core.s04_models import User

# --- password hashing settings -------------------------------------------

ALGORITHM = "pbkdf2_sha256"

# OWASP's 2023 floor for PBKDF2-HMAC-SHA256. It is deliberately slow: the
# whole point is that someone who steals the database file cannot try
# billions of guesses per second against it. hashlib runs this in C, so the
# cost to a legitimate sign-in is a fraction of a second.
ITERATIONS = 600_000

SALT_BYTES = 16

# --- password rules -------------------------------------------------------

MIN_PASSWORD_LENGTH = 8

# A cap, because the whole string is fed to the hash. PBKDF2's cost does not
# grow with input length, but there is no reason to accept a megabyte.
MAX_PASSWORD_LENGTH = 128

MAX_EMAIL_LENGTH = 254  # the limit a mail address is allowed to be

# The ones that actually turn up at the top of every breach corpus. This is a
# speed bump for the obvious cases, not a substitute for a real deny-list.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwerty123", "qwertyuiop", "iloveyou", "admin123",
    "welcome1", "letmein1", "abc12345", "football", "monkey123",
}

# --- sign-in lockout ------------------------------------------------------

MAX_FAILED_ATTEMPTS = 8
LOCKOUT_SECONDS = 900  # 15 minutes

# email -> {"failures": int, "locked_until": datetime | None}
#
# In memory, so it clears when the server restarts. A real deployment keeps
# this in the database or a cache; for a single local process this is enough
# to stop an unattended script grinding through a password list.
_failures: dict[str, dict] = {}


# --- errors ---------------------------------------------------------------

class AccountError(Exception):
    """Base class, so a caller can catch everything here at once."""


class InvalidEmail(AccountError):
    pass


class WeakPassword(AccountError):
    pass


class EmailTaken(AccountError):
    pass


class BadCredentials(AccountError):
    pass


class AccountLocked(AccountError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


# --- email ----------------------------------------------------------------

# Deliberately permissive. Validating an address by pattern is a losing game;
# this only rejects what is obviously not an address, and delivery would be
# the real test if this app ever sent mail.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def normalize_email(raw: str) -> str:
    """Trim and lowercase, then check it looks like an address.

    Lowercasing matters more than it looks: without it 'Guru@x.com' and
    'guru@x.com' become two accounts, and the person who made the first one
    cannot sign in to it.
    """
    email = (raw or "").strip().lower()

    if not email:
        raise InvalidEmail("Enter your email address.")
    if len(email) > MAX_EMAIL_LENGTH:
        raise InvalidEmail("That email address is too long.")
    if not EMAIL_PATTERN.match(email):
        raise InvalidEmail("That does not look like an email address.")

    return email


def clean_name(raw: str, email: str) -> str:
    """A display name, falling back to the part of the email before the @."""
    name = (raw or "").strip()
    if name:
        return name[:60]
    return email.split("@")[0][:60]


# --- passwords ------------------------------------------------------------

def check_password_strength(password: str) -> None:
    """Raise WeakPassword if it fails the rules. Return nothing if it passes.

    The rules are short on purpose. Long lists of character-class demands
    push people towards 'Passw0rd!', which is worse than a longer plain one.
    Length does most of the work.
    """
    if not password:
        raise WeakPassword("Choose a password.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Use at least {MIN_PASSWORD_LENGTH} characters."
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Keep it under {MAX_PASSWORD_LENGTH} characters."
        )

    if password.lower() in COMMON_PASSWORDS:
        raise WeakPassword("That password is one of the most common ones. Pick another.")

    if len(set(password)) < 4:
        raise WeakPassword("That is too repetitive. Mix in some other characters.")


def hash_password(password: str, iterations: int | None = None) -> str:
    """Turn a password into something safe to store.

    Three things make this safe, and all three are necessary:

    - a random salt per user, so two people with the same password get
      different stored values and one rainbow table cannot cover both;
    - a slow function, so guessing is expensive;
    - the parameters stored alongside the hash, so ITERATIONS can be raised
      later without invalidating everybody's existing password.

    Format: algorithm$iterations$salt$hash, all base64 where binary.
    """
    rounds = iterations or ITERATIONS
    salt = secrets.token_bytes(SALT_BYTES)

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)

    return "$".join([
        ALGORITHM,
        str(rounds),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    ])


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash.

    Uses compare_digest rather than ==. A plain comparison stops at the first
    differing byte, and the time it took leaks how much of the hash was
    guessed correctly.
    """
    try:
        algorithm, rounds, salt_b64, expected_b64 = stored.split("$")
    except (ValueError, AttributeError):
        # A corrupt or hand-edited row must fail closed, not crash.
        return False

    if algorithm != ALGORITHM:
        return False

    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(expected_b64)
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(rounds)
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(derived, expected)


# A hash of nothing in particular, verified against when the email is unknown
# so that a missing account takes the same time as a wrong password. Without
# it, response time alone tells an attacker which addresses are registered.
_DUMMY_HASH: str | None = None


def _burn_time_like_a_real_check(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _DUMMY_HASH)


# --- lockout --------------------------------------------------------------

def _lock_state(email: str) -> dict:
    return _failures.setdefault(email, {"failures": 0, "locked_until": None})


def _raise_if_locked(email: str, now: dt.datetime) -> None:
    state = _lock_state(email)
    locked_until = state["locked_until"]

    if locked_until is None:
        return

    if now >= locked_until:
        # The lock has expired. Start the count again from zero.
        state["failures"] = 0
        state["locked_until"] = None
        return

    seconds = int((locked_until - now).total_seconds()) + 1
    minutes = max(1, round(seconds / 60))
    raise AccountLocked(
        f"Too many failed attempts. Try again in about {minutes} minute"
        f"{'s' if minutes != 1 else ''}.",
        retry_after=seconds,
    )


def _record_failure(email: str, now: dt.datetime) -> None:
    state = _lock_state(email)
    state["failures"] += 1
    if state["failures"] >= MAX_FAILED_ATTEMPTS:
        state["locked_until"] = now + dt.timedelta(seconds=LOCKOUT_SECONDS)


def _clear_failures(email: str) -> None:
    _failures.pop(email, None)


def clear_all_failures() -> None:
    """Reset the lockout table. For tests, and for signing out."""
    _failures.clear()


# --- the two operations ---------------------------------------------------

def create_account(
    session,
    email: str,
    password: str,
    name: str = "",
    now: dt.datetime | None = None,
) -> User:
    """Register a new account.

    Note that this DOES reveal whether an address is already registered —
    'that email is already registered' is the only message that lets someone
    realise they should be signing in instead. Sign-in stays silent about it.
    """
    now = now or dt.datetime.now()

    address = normalize_email(email)
    check_password_strength(password)

    existing = session.execute(
        select(User).where(User.email == address)
    ).scalar_one_or_none()

    if existing is not None:
        raise EmailTaken("That email is already registered. Sign in instead.")

    user = User(
        email=address,
        display_name=clean_name(name, address),
        password_hash=hash_password(password),
        last_signed_in_at=now,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return user


def authenticate(
    session,
    email: str,
    password: str,
    now: dt.datetime | None = None,
) -> User:
    """Check an email and password, and return the account.

    Every failure raises the same BadCredentials with the same wording,
    whether the address is unknown or the password is wrong. Saying which
    one it was hands over a list of who has an account here.
    """
    now = now or dt.datetime.now()

    address = normalize_email(email)
    _raise_if_locked(address, now)

    user = session.execute(
        select(User).where(User.email == address)
    ).scalar_one_or_none()

    if user is None:
        _burn_time_like_a_real_check(password)
        _record_failure(address, now)
        raise BadCredentials("Email or password is incorrect.")

    if not verify_password(password, user.password_hash):
        _record_failure(address, now)
        raise BadCredentials("Email or password is incorrect.")

    _clear_failures(address)
    user.last_signed_in_at = now
    session.commit()
    session.refresh(user)

    return user


def count_accounts(session) -> int:
    """How many accounts exist. Used to greet the very first user."""
    return session.execute(select(func.count(User.id))).scalar_one()
