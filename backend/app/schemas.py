"""Pydantic request/response models.

House rule: money leaves the API as a 2-decimal STRING, never a JSON number.
A float would quietly turn 409.50 into 409.49999999999994 somewhere down the
line, and JavaScript has no decimal type to receive it safely.
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class UploadResult(BaseModel):
    """What POST /api/upload reports back."""

    upload_id: int
    filename: str
    rows_parsed: int
    imported: int
    skipped: int
    duplicates: int


class TransactionOut(BaseModel):
    """One transaction as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    description: str
    amount: Decimal
    direction: str
    category: str
    category_source: str
    confidence: float | None = None

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class TransactionPage(BaseModel):
    """A page of transactions.

    `total` is the count matching the filters, not the length of `items` —
    the table needs it to show "showing 100 of 205".
    """

    total: int
    limit: int
    offset: int
    items: list[TransactionOut]
