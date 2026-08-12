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


class Anomaly(BaseModel):
    """One unusually large debit, with the sentence explaining why."""

    id: int
    date: dt.date
    description: str
    amount: Decimal
    direction: str
    category: str
    reason: str

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int

    @field_serializer("total")
    def serialize_total(self, total: Decimal) -> str:
        return f"{total:.2f}"


class MerchantTotal(BaseModel):
    merchant: str
    total: Decimal
    count: int

    @field_serializer("total")
    def serialize_total(self, total: Decimal) -> str:
        return f"{total:.2f}"


class LabellerCount(BaseModel):
    """How many rows a given labeller ('rule', 'model', 'user') accounts for."""

    source: str
    count: int


class Summary(BaseModel):
    """GET /api/summary. Spending excludes transfers — see aggregations.py."""

    total_spent: Decimal
    total_income: Decimal
    net: Decimal
    transaction_count: int
    by_category: list[CategoryTotal]
    by_category_source: list[LabellerCount]
    top_merchants: list[MerchantTotal]

    @field_serializer("total_spent", "total_income", "net")
    def serialize_money(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class TrendPoint(BaseModel):
    month: str
    spent: Decimal
    income: Decimal

    @field_serializer("spent", "income")
    def serialize_money(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class OtpRequest(BaseModel):
    """A phone number, in whatever shape the user typed it."""

    phone: str


class OtpChallenge(BaseModel):
    """The issued challenge.

    `demo_code` exists only because there is no SMS provider to deliver the
    code with. A real API never returns the code it just issued.
    """

    phone: str
    display_phone: str
    expires_in: int
    resend_in: int
    attempts_allowed: int
    demo_code: str


class OtpVerify(BaseModel):
    phone: str
    code: str


class OtpVerification(BaseModel):
    verified: bool
    phone: str
    display_phone: str


class CategoryOption(BaseModel):
    """A category and how many transactions currently carry it."""

    category: str
    count: int


class SheetSource(BaseModel):
    """One worksheet within an uploaded file."""

    sheet_name: str | None
    count: int


class UploadSource(BaseModel):
    """One uploaded file and the sheets it contributed.

    This is what the source filter is built from, so the options always match
    what is actually in the database rather than a hardcoded list.
    """

    upload_id: int
    filename: str
    uploaded_at: dt.datetime
    count: int
    sheets: list[SheetSource]


class UploadDeleted(BaseModel):
    upload_id: int
    filename: str
    transactions_deleted: int


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
