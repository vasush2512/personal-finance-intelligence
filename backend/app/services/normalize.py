"""Turn a raw bank narration into something matchable.

Bank descriptions look like:
    UPI/DR/412345678901/SWIGGY/HDFC/swiggyupi@icici/Payment
    POS 4512XXXXXXXX1234 AMAZON PAY INDIA        MUMBAI
    NEFT-AXISCN0123456789-RENT MARCH

The rules and the ML model both work on the normalized form, so a
description only ever has to be cleaned in one place.
"""

import re

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


def fingerprint(date_iso: str, normalized_desc: str, amount: str, direction: str) -> str:
    """Stable hash used to detect a re-uploaded statement (PRD 7.2)."""
    import hashlib

    key = f"{date_iso}|{normalized_desc}|{amount}|{direction}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
