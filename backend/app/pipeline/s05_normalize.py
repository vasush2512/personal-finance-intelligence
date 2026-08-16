"""Turn a raw bank narration into something matchable.

Bank descriptions look like:
    UPI/DR/412345678901/SWIGGY/HDFC/swiggyupi@icici/Payment
    POS 4512XXXXXXXX1234 AMAZON PAY INDIA        MUMBAI
    NEFT-AXISCN0123456789-RENT MARCH

The rules and the ML model both work on the normalized form, so a
description only ever has to be cleaned in one place.
"""

import re
from functools import lru_cache

from app.core.s01_constants import CATEGORIES

# Both extractors below are pure functions of their input strings, and both are
# called once per row over windows of tens of thousands. Bank narrations repeat
# heavily — the same merchant, the same template, thousands of times — so the
# cache hits far more often than it misses. Bounded, because a statement with
# entirely unique narrations must not grow this without limit.
_EXTRACT_CACHE_SIZE = 16384

# Payment-rail prefixes that carry no information about the merchant.
_RAIL_PREFIXES = re.compile(
    r"\b(upi|neft|imps|rtgs|pos|ach|ecs|nach|atm|inb|mmt|chq|clg|vps|mps)\b[\s/:-]*",
    re.IGNORECASE,
)

# Bank-side noise words that appear on nearly every row.
_NOISE = re.compile(
    r"\b(dr|cr|txn|trf|transfer to|transfer from|payment from|payment to|"
    r"ref no|refno|ref|inf|bil|mob|onl|ib|eba|paytm qr|razorpay|payu|billdesk|"
    r"ccavenue|bharatpe|phonepe|gpay|google pay|paytm)\b",
    re.IGNORECASE,
)

# Bank identifiers that pollute UPI strings.
_BANKS = re.compile(
    r"\b(hdfc|icici|sbi|axis|kotak|yesb|idfc|pnb|boi|canara|indus|federal|ubin|"
    r"okhdfcbank|oksbi|okicici|okaxis|ybl|apl|ibl)\b",
    re.IGNORECASE,
)

# Must NOT be \S+@\S+ : bank narrations often contain no spaces at all
# ("UPI/DR/123/BLINKIT/HDFC/blinkit@ybl/Groceries"), and the greedy version
# swallows the entire string including the merchant name.
_UPI_HANDLE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9._-]+")
_LONG_DIGITS = re.compile(r"\b\w*\d{4,}\w*\b")   # ref numbers, masked cards
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_description(raw: str) -> str:
    """Lowercase, strip rails/refs/handles/punctuation, collapse whitespace."""
    if not raw:
        return ""

    text = str(raw).lower()
    text = _UPI_HANDLE.sub(" ", text)      # handles first: they contain @ and dots
    text = _LONG_DIGITS.sub(" ", text)     # then reference numbers
    text = _NON_ALNUM.sub(" ", text)       # now safe to drop punctuation
    text = _RAIL_PREFIXES.sub(" ", text)
    text = _BANKS.sub(" ", text)
    text = _NOISE.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text


# --- merchant and payment method ------------------------------------------
#
# Both are derived from the narration on read rather than stored as columns.
# The inputs (description, normalized_description) are already on every row, so
# a column would be a second copy that could fall out of step — and adding one
# to an existing table means backfilling every row before the UI can trust it.
# If merchant ever needs its own index for grouping at scale, that is the point
# to promote it to a column, not before.

# The rail a payment travelled on, in the order a narration mentions it. UPI
# before IMPS because "UPI/DR/.../IMPS-REF" is a UPI payment carrying an IMPS
# reference, and the first token is the one that describes the transaction.
_PAYMENT_RAILS = [
    ("UPI", r"\bupi\b"),
    ("Card", r"\bpos\b|\becom\b|\bcard\b"),
    ("ATM", r"\batm\b"),
    ("NEFT", r"\bneft\b"),
    ("RTGS", r"\brtgs\b"),
    ("IMPS", r"\bimps\b"),
    ("Cheque", r"\bchq\b|\bcheque\b|\bclg\b"),
    ("Auto-debit", r"\bach\b|\becs\b|\bnach\b|\bsi\b|\bmandate\b"),
    ("Net banking", r"\binb\b|\bib\b|\bnetbank"),
]

_COMPILED_RAILS = [
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _PAYMENT_RAILS
]

# Words that survive normalization but are not a merchant name — a narration
# beginning with one of these means the real merchant is the next token.
_NOT_A_MERCHANT = {
    "payment", "order", "purchase", "spend", "txn", "transaction", "debit",
    "credit", "bill", "recharge", "fee", "charges", "charge", "to", "from",
    "and", "the", "for", "via", "by", "at", "on", "of",
}


# Words that describe what a payment was FOR rather than who it was to. A
# category name in this position is a tag the bank appended, not a shop.
_PURPOSE_WORDS = set(CATEGORIES) | {
    "grocery", "dining", "fuel", "travel", "medical", "salary", "rent",
    "subscription", "emi", "loan", "premium", "topup", "wallet", "cashback",
    # Statements append the period a payment covers: "RENT MARCH", "SALARY MAY".
    "jan", "january", "feb", "february", "mar", "march", "apr", "april",
    "may", "jun", "june", "jul", "july", "aug", "august", "sep", "sept",
    "september", "oct", "october", "nov", "november", "dec", "december",
}


@lru_cache(maxsize=_EXTRACT_CACHE_SIZE)
def extract_payment_method(raw: str):
    """'UPI/DR/998877/SWIGGY/HDFC/...' -> 'UPI'. None when nothing says.

    Read from the RAW narration, not the normalized one: normalization strips
    rail prefixes precisely because they say nothing about the merchant, which
    is the opposite of what is wanted here.
    """
    if not raw:
        return None
    text = str(raw)
    for name, pattern in _COMPILED_RAILS:
        if pattern.search(text):
            return name
    return None


@lru_cache(maxsize=_EXTRACT_CACHE_SIZE)
def extract_merchant(raw: str, normalized: str = None) -> str:
    """A displayable merchant name from a bank narration.

    'UPI/DR/998877665544/SWIGGY/HDFC/swiggy@icici/Payment' -> 'Swiggy'

    Works from the normalized form, which has already had the rails, reference
    numbers, UPI handles and bank identifiers removed — so what is left is
    mostly the merchant plus a few filler words. Leading filler is dropped, and
    up to three words are kept so 'reliance fresh' and 'house rent' survive
    intact rather than becoming 'reliance' and 'house'.

    This is deliberately not a lookup table. A fixed list of merchants covers
    the demo statement and nothing else; the rule generalises to any narration
    and can be tightened without anyone maintaining a dictionary.
    """
    text = normalized if normalized is not None else normalize_description(raw)
    words = [word for word in (text or "").split() if word]

    # Drop filler, and any bare number: a reference fragment short enough to
    # survive the 4+ digit strip ("UPI/DR/1/BLINKIT/...") is still not a shop.
    meaningful = [
        word
        for word in words
        if word not in _NOT_A_MERCHANT and not word.isdigit()
    ]
    candidates = (meaningful or words)[:3]

    if not candidates:
        return "Unknown"

    # Stop at a trailing purpose tag. UPI narrations routinely end with what
    # the payment was for — ".../BLINKIT/HDFC/blinkit@ybl/Groceries" — and
    # without this the merchant reads "Blinkit Groceries", which is not a shop.
    # The first word is always kept: when the purpose tag *is* the whole
    # description ("RENT MARCH") there is nothing better to show.
    chosen = [candidates[0]]
    for word in candidates[1:]:
        if word in _PURPOSE_WORDS:
            break
        chosen.append(word)

    return " ".join(word.capitalize() for word in chosen)


def fingerprint(date_iso: str, normalized_desc: str, amount: str, direction: str) -> str:
    """Stable hash used to detect a re-uploaded statement (PRD 7.2)."""
    import hashlib

    key = f"{date_iso}|{normalized_desc}|{amount}|{direction}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
