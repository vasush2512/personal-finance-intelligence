"""Pydantic request/response models.

House rule: money leaves the API as a 2-decimal STRING, never a JSON number.
A float would quietly turn 409.50 into 409.49999999999994 somewhere down the
line, and JavaScript has no decimal type to receive it safely.
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.constants import CATEGORIES


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


class RetrainResult(BaseModel):
    """What POST /api/model/retrain reports back.

    holdout_accuracy is agreement with the keyword rules, not correctness —
    the rules produced the training labels. It only becomes a measure of
    correctness once enough user corrections are in the training set.
    """

    trained: bool
    labelled_rows: int
    classes: list[str]
    holdout_accuracy: float
    model_path: str


class TransactionUpdate(BaseModel):
    """Body of PATCH /api/transactions/{id}.

    Category is the only editable field. Date, amount and description come
    from the bank and are not the user's to rewrite.
    """

    category: str

    @field_validator("category")
    @classmethod
    def category_must_be_known(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(
                f"Unknown category {value!r}. Valid: {', '.join(CATEGORIES)}"
            )
        return value


class TransactionPage(BaseModel):
    """A page of transactions.

    `total` is the count matching the filters, not the length of `items` —
    the table needs it to show "showing 100 of 205".
    """

    total: int
    limit: int
    offset: int
    items: list[TransactionOut]
