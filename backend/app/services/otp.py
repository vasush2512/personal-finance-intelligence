"""One-time codes for the phone sign-in screen.

READ THIS FIRST — what this is and is not
-----------------------------------------
Delivery depends on configuration, and so does how much this can be trusted.

  * With an SMS provider configured (see services/sms.py), the code goes to
    the phone and is NEVER returned by the API or written to a log. That is
    the only arrangement in which a one-time code means anything.
  * With no provider — the default — the code comes back in the response and
    is shown on screen, clearly labelled. Convenient for development, and
    obviously not a secret.

Either way, verifying does not create a session. No token is issued, nothing
is signed, and every other endpoint answers regardless; the dashboard gates
itself in the browser, which anyone can bypass. Codes live in a module-level
dict, so restarting the server forgets them and a second worker process
would not see them.

What is modelled properly, because these are the parts worth understanding:
expiry, a cap on guesses, a resend cooldown, a daily send cap, single use,
and a comparison that does not leak how much of the code was right.

PRD section 3 keeps accounts and authentication as non-goals. This exists
because it was asked for.
"""

import datetime as dt
import hmac
import re
import secrets

from app.services import sms

CODE_LENGTH = 6
CODE_TTL_SECONDS = 300        # five minutes
RESEND_COOLDOWN_SECONDS = 30
MAX_ATTEMPTS = 5

# A cooldown stops a fast loop; this stops a slow one. Without it, an open
# endpoint that sends real SMS is an SMS bomber pointed at any number
# somebody types, billed to whoever owns the provider account.
MAX_SENDS_PER_PHONE_PER_DAY = 10

# Indian mobile numbers: ten digits starting 6-9, with the usual decorations.
_DIGITS = re.compile(r"\D+")


class OtpError(Exception):
    """Anything the caller did wrong. Carries the message for the API."""


class InvalidPhone(OtpError):
    pass


class TooSoon(OtpError):
    """A resend was asked for before the cooldown elapsed."""

    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


class NoChallenge(OtpError):
    pass


class CodeExpired(OtpError):
    pass


class TooManyAttempts(OtpError):
    pass


class DailyLimitReached(OtpError):
    """This number has been sent enough codes for one day."""


class DeliveryFailed(OtpError):
    """The provider would not take the message."""


class WrongCode(OtpError):
    def __init__(self, message, attempts_left):
        super().__init__(message)
        self.attempts_left = attempts_left


# phone -> {"code", "expires_at", "sent_at", "attempts"}
_challenges = {}

# phone -> {"date": date, "count": int}
_daily_sends = {}


def normalize_phone(raw: str) -> str:
    """'+91 98765 43210' / '098765 43210' -> '9876543210'.

    Everything downstream keys on the normalized form, so the same phone
    typed three different ways is one challenge rather than three.
    """
    digits = _DIGITS.sub("", raw or "")

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10 or digits[0] not in "6789":
        raise InvalidPhone(
            "Enter a 10-digit Indian mobile number starting with 6, 7, 8 or 9."
        )
    return digits


def format_phone(phone: str) -> str:
    """'9876543210' -> '+91 98765 43210', for display."""
    return f"+91 {phone[:5]} {phone[5:]}"


def _generate_code() -> str:
    """A zero-padded six-digit code from the cryptographic generator.

    secrets, not random: once a code actually travels to a phone and is the
    only thing standing between a stranger and a sign-in, it must not come
    from a generator whose next output can be predicted from earlier ones.
    """
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def _count_send(phone: str, now: dt.datetime) -> None:
    """Record a send, refusing once this number has had its day's worth."""
    today = now.date()
    record = _daily_sends.get(phone)

    if record is None or record["date"] != today:
        record = {"date": today, "count": 0}
        _daily_sends[phone] = record

    if record["count"] >= MAX_SENDS_PER_PHONE_PER_DAY:
        raise DailyLimitReached(
            "This number has been sent too many codes today. Try again tomorrow."
        )

    record["count"] += 1


def request_code(raw_phone: str, now=None) -> dict:
    """Issue a code for this number. Returns the challenge, code included.

    Raises TooSoon when a code was issued within the cooldown, which is what
    stops a resend button from becoming a way to spam someone's phone.
    """
    now = now or dt.datetime.now()
    phone = normalize_phone(raw_phone)

    existing = _challenges.get(phone)
    if existing:
        age = (now - existing["sent_at"]).total_seconds()
        if age < RESEND_COOLDOWN_SECONDS:
            raise TooSoon(
                "A code was just sent. Wait a moment before asking for another.",
                retry_after=int(RESEND_COOLDOWN_SECONDS - age) + 1,
            )

    _count_send(phone, now)

    code = _generate_code()

    # Send before storing. If the provider refuses, the previous challenge
    # stays valid and the caller has not silently lost the code they already
    # have in their hand.
    try:
        delivery = sms.send_code(phone, code)
    except sms.SmsError as error:
        raise DeliveryFailed(str(error))

    _challenges[phone] = {
        "code": code,
        "sent_at": now,
        "expires_at": now + dt.timedelta(seconds=CODE_TTL_SECONDS),
        "attempts": 0,
    }

    challenge = {
        "phone": phone,
        "display_phone": format_phone(phone),
        "expires_in": CODE_TTL_SECONDS,
        "resend_in": RESEND_COOLDOWN_SECONDS,
        "attempts_allowed": MAX_ATTEMPTS,
        "delivery": delivery,
        "demo_code": None,
    }

    # The code comes back ONLY when nothing was able to carry it. The moment
    # a provider is configured this stays null, because a one-time code the
    # API hands out is not one.
    if delivery == "on_screen":
        challenge["demo_code"] = code

    return challenge


def verify_code(raw_phone: str, code: str, now=None) -> dict:
    """Check a code. Consumed on success, counted against on failure."""
    now = now or dt.datetime.now()
    phone = normalize_phone(raw_phone)

    challenge = _challenges.get(phone)
    if challenge is None:
        raise NoChallenge("Ask for a code first.")

    if now >= challenge["expires_at"]:
        del _challenges[phone]
        raise CodeExpired("That code has expired. Ask for a new one.")

    if challenge["attempts"] >= MAX_ATTEMPTS:
        del _challenges[phone]
        raise TooManyAttempts("Too many wrong codes. Ask for a new one.")

    submitted = _DIGITS.sub("", code or "")

    # compare_digest rather than ==: a plain comparison stops at the first
    # wrong character, and the time it took says how much was right.
    if not hmac.compare_digest(submitted, challenge["code"]):
        challenge["attempts"] += 1
        left = MAX_ATTEMPTS - challenge["attempts"]
        if left <= 0:
            del _challenges[phone]
            raise TooManyAttempts("Too many wrong codes. Ask for a new one.")
        raise WrongCode("That code is not right.", attempts_left=left)

    # Single use. A code that still works after being used is not one-time.
    del _challenges[phone]

    return {
        "verified": True,
        "phone": phone,
        "display_phone": format_phone(phone),
    }


def forget(raw_phone: str) -> None:
    """Drop any outstanding challenge. Used by sign-out."""
    try:
        _challenges.pop(normalize_phone(raw_phone), None)
    except InvalidPhone:
        pass


def clear_all() -> None:
    """Wipe every challenge and send count. For tests."""
    _challenges.clear()
    _daily_sends.clear()
