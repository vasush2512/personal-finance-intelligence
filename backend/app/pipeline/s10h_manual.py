"""Turning a manual entry into a transaction. Pure logic, no database.

A manually entered expense becomes an ordinary row in the ordinary
transactions table. That is the whole design: there is no second model, no
second analytics path, and nothing downstream needs to know or care where a
row came from. Everything the existing pipeline expects — a normalised
description, a direction, a fingerprint — is produced here so the rest of the
system cannot tell the difference.

The one place manual entries must differ is the fingerprint. On a statement it
is a hash of the row's own values, and its unique index is what makes
re-uploading a file a safe no-op. Applied to manual entry that would be wrong:
two ₹120 coffees bought on the same day are two real payments, and the second
one is not a duplicate of the first. So a manual fingerprint carries a random
component and never collides.

The "you typed this and then uploaded a statement containing it" case is real,
and it is handled where it belongs — by the existing near-duplicate detector,
which was built for exactly that shape of problem.
"""

import datetime as dt
import secrets
from decimal import Decimal, ROUND_HALF_UP

from app.core.s01_constants import ENTRY_MANUAL, PAYMENT_METHODS, UNCATEGORIZED
from app.pipeline.s05_normalize import normalize_description

# Enough randomness that two manual rows never collide, short enough to leave
# room for the readable prefix inside the 64-character column.
_TOKEN_BYTES = 12

MAX_AMOUNT = Decimal("100000000.00")


class InvalidEntry(ValueError):
    """A manual entry that cannot become a transaction, with a reason."""


def clean_amount(value) -> Decimal:
    """Whatever the form sent -> a positive Decimal, or a readable refusal."""
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except Exception:
        raise InvalidEntry("Enter the amount as a number, for example 250 or 250.50.")

    if not amount.is_finite():
        raise InvalidEntry("That amount is not a number.")
    if amount <= 0:
        raise InvalidEntry(
            "The amount has to be more than zero. Whether it is money in or "
            "money out is set by the Expense/Income choice, not by a minus sign."
        )
    if amount > MAX_AMOUNT:
        raise InvalidEntry("That amount is larger than this app can record.")

    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clean_date(value, today=None) -> dt.date:
    """An ISO date string or date -> a date, refusing the impossible."""
    today = today or dt.date.today()

    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        entry_date = value
    else:
        try:
            entry_date = dt.date.fromisoformat(str(value).strip())
        except Exception:
            raise InvalidEntry("Give the date as YYYY-MM-DD.")

    # A future date is refused rather than stored: it would sit outside every
    # complete month the forecast is built from and quietly distort the one
    # figure that depends on months being finished.
    if entry_date > today:
        raise InvalidEntry("That date is in the future. Record it on the day it happens.")
    if entry_date.year < 1990:
        raise InvalidEntry("That date is too far in the past to be a real transaction.")

    return entry_date


def clean_direction(value) -> str:
    text = str(value or "").strip().lower()
    if text in ("debit", "expense", "out"):
        return "debit"
    if text in ("credit", "income", "in"):
        return "credit"
    raise InvalidEntry("Choose whether this is an expense or income.")


def clean_payment_method(value) -> str:
    """Match a known method case-insensitively; blank is allowed."""
    text = str(value or "").strip()
    if not text:
        return ""
    for known in PAYMENT_METHODS:
        if known.lower() == text.lower():
            return known
    raise InvalidEntry(
        f"Unknown payment method {text!r}. Choose one of: {', '.join(PAYMENT_METHODS)}."
    )


def clean_merchant(value) -> str:
    """The name as typed, trimmed.

    Deliberately NOT run through merchant normalisation. That exists to make
    sense of bank narrations; a name a person typed is already the answer it
    would be trying to reach, and "correcting" it would be the app overruling
    someone about their own entry.
    """
    return " ".join(str(value or "").split())[:80]


def manual_fingerprint(prefix: str = "manual") -> str:
    """A fingerprint that is unique by construction. See the module docstring."""
    return f"{prefix}-{secrets.token_hex(_TOKEN_BYTES)}"


def build_manual_transaction(
    *, amount, date, direction, category=None, merchant="", payment_method="",
    notes="", today=None,
):
    """A validated manual entry, in the shape the importer already stores.

    Returns a plain dict so this stays testable without a database and without
    a request. Category may be None — the caller decides whether to accept a
    suggestion, and the store layer records who chose it.
    """
    amount = clean_amount(amount)
    entry_date = clean_date(date, today=today)
    direction = clean_direction(direction)
    payment_method = clean_payment_method(payment_method)
    merchant = clean_merchant(merchant)

    # The description is what search, the categoriser and the duplicate
    # detector all read, so it has to be assembled from what the user gave
    # rather than left blank.
    description = merchant or (notes or "").strip()[:80] or "Manual entry"

    return {
        "date": entry_date,
        "description": description,
        "normalized_description": normalize_description(description),
        "merchant_name": merchant,
        "amount": amount,
        "direction": direction,
        "category": category or UNCATEGORIZED,
        "payment_method": payment_method,
        "notes": (notes or "").strip()[:500] or None,
        "entry_source": ENTRY_MANUAL,
        "fingerprint": manual_fingerprint(),
    }
