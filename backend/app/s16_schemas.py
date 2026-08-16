"""Pydantic request/response models.

House rule: money leaves the API as a 2-decimal STRING, never a JSON number.
A float would quietly turn 409.50 into 409.49999999999994 somewhere down the
line, and JavaScript has no decimal type to receive it safely.
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.core.s01_constants import CATEGORIES


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
    # Derived from the narration by a property on the model — see s04_models.
    merchant: str
    amount: Decimal
    direction: str
    category: str
    category_source: str
    confidence: float | None = None

    # Manual-entry fields. Null on every imported row, which is most of them —
    # added rather than replacing anything, so existing consumers are
    # unaffected.
    entry_source: str | None = None
    payment_method: str | None = None
    notes: str | None = None
    # Populated by the router, not read off the model: tags live in a join
    # table and are fetched for a whole page at once.
    tags: list[str] = []

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


class SignUpRequest(BaseModel):
    """Body of POST /api/auth/sign-up."""

    email: str
    password: str
    name: str = ""


class SignInRequest(BaseModel):
    """Body of POST /api/auth/sign-in."""

    email: str
    password: str


class AccountOut(BaseModel):
    """An account as the API returns it.

    There is no password field here, and there must never be one. A response
    model that cannot name the hash cannot leak it by accident, which is the
    main reason this is a separate class from the User model.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str

    # The session token, present only on the sign-up and sign-in responses.
    # Every other endpoint that returns an account leaves it None, so a token
    # cannot leak from a listing.
    token: str | None = None


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


class AnomalyFactor(BaseModel):
    """One contributor to an anomaly score, on a 0-100 scale."""

    key: str
    label: str
    value: int
    detail: str


class AnomalyAnalysis(BaseModel):
    """Why a transaction was or was not flagged.

    `available` is false when the category has too little history to compare
    against — the UI shows `reason` instead of a score, rather than a confident
    number built on three transactions.
    """

    available: bool
    reason: str | None = None
    score: int | None = None
    factors: list[AnomalyFactor] = []
    baseline: Decimal | None = None
    ratio: float | None = None
    peer_count: int | None = None
    lookback_days: int | None = None
    threshold: Decimal | None = None
    explanation: str | None = None

    @field_serializer("baseline", "threshold")
    def serialize_money(self, amount: Decimal | None) -> str | None:
        return None if amount is None else f"{amount:.2f}"


class TransactionDetail(BaseModel):
    """One transaction with the analysis behind it, for the detail drawer.

    A superset of TransactionOut rather than a replacement: the list endpoint
    stays cheap, and only opening a row pays for the peer query.
    """

    id: int
    date: dt.date
    description: str
    normalized_description: str
    merchant: str
    payment_method: str | None = None
    amount: Decimal
    direction: str
    category: str
    category_source: str
    confidence: float | None = None
    sheet_name: str | None = None
    upload_id: int | None = None
    is_anomaly: bool
    anomaly: AnomalyAnalysis | None = None

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class HealthComponent(BaseModel):
    """One weighted part of the financial health score."""

    key: str
    label: str
    value: int
    weight: int
    detail: str


class FinancialHealth(BaseModel):
    """A 0-100 summary of what already happened — not a forecast or a rating.

    Withheld entirely below a couple of months of history, because spending
    consistency cannot be described from a single statement.
    """

    available: bool
    score: int | None = None
    band: str | None = None
    components: list[HealthComponent] = []
    reason: str | None = None


class DuplicateSide(BaseModel):
    """One half of a suggested duplicate pair."""

    id: int
    date: dt.date
    description: str
    merchant: str
    payment_method: str | None = None
    amount: Decimal
    direction: str
    category: str

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class DuplicatePair(BaseModel):
    """Two transactions that may be one payment recorded twice.

    `verdict` is null until the user answers: true means they confirmed it,
    false means they said it is genuinely two transactions. Nothing is ever
    deleted automatically — only the person who made the payments knows.
    """

    first: DuplicateSide
    second: DuplicateSide
    score: int
    reasons: list[str]
    days_apart: int
    amount: Decimal
    merchant: str
    verdict: bool | None = None

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class DuplicateVerdictRequest(BaseModel):
    """Body of POST /api/duplicates/verdict."""

    first_id: int
    second_id: int
    is_duplicate: bool


class RecurringPayment(BaseModel):
    """A merchant being paid on a regular rhythm.

    `next_expected` is only present when the intervals are regular enough for a
    date to mean something — a prediction attached to a weak signal reads as a
    commitment the data cannot back.
    """

    merchant: str
    category: str | None = None
    frequency: str
    typical_gap_days: int
    occurrences: int
    average_amount: Decimal
    last_amount: Decimal
    last_date: dt.date
    next_expected: dt.date | None = None
    confidence: int
    amount_varies: bool

    @field_serializer("average_amount", "last_amount")
    def serialize_money(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class RecurringSummary(BaseModel):
    payments: list[RecurringPayment]
    monthly_total: Decimal
    lookback_days: int

    @field_serializer("monthly_total")
    def serialize_total(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class Insight(BaseModel):
    """One plain-English observation, with the evidence behind it."""

    key: str
    tone: str
    headline: str
    detail: str


class MonthProgress(BaseModel):
    """How the month being projected is tracking so far."""

    month: str
    spent_so_far: Decimal
    projected: Decimal
    share_of_projection: int
    remaining: Decimal

    @field_serializer("spent_so_far", "projected", "remaining")
    def serialize_money(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class CashFlowForecast(BaseModel):
    """A projection from complete months — not a prediction of the future.

    Every figure here describes months that already happened. `basis` carries
    the sentence explaining which months, and `spending_low`/`spending_high`
    are the real smallest and largest of them, so the width of the uncertainty
    is visible rather than implied.
    """

    available: bool
    reason: str | None = None
    month: str | None = None
    months_used: int = 0
    from_month: str | None = None
    to_month: str | None = None
    projected_spending: Decimal | None = None
    projected_income: Decimal | None = None
    projected_net: Decimal | None = None
    spending_low: Decimal | None = None
    spending_high: Decimal | None = None
    committed: Decimal | None = None
    confidence: int | None = None
    basis: str | None = None
    progress: MonthProgress | None = None

    @field_serializer(
        "projected_spending",
        "projected_income",
        "projected_net",
        "spending_low",
        "spending_high",
        "committed",
    )
    def serialize_money(self, amount: Decimal | None) -> str | None:
        return None if amount is None else f"{amount:.2f}"


class MonthlyStory(BaseModel):
    """One month written as paragraphs."""

    available: bool
    month: str
    title: str
    reason: str | None = None
    paragraphs: list[str] = []


class SourceShare(BaseModel):
    """How many rows one labeller accounts for."""

    source: str
    label: str
    count: int
    share: float


class ConfidenceBucket(BaseModel):
    """How many model-labelled rows fell in one confidence band."""

    label: str
    low: float
    high: float
    count: int


class CorrectionCount(BaseModel):
    source: str
    label: str
    count: int


class Confusion(BaseModel):
    """A wrong answer the classifier gave, and what it was corrected to."""

    from_category: str
    to_category: str
    count: int


class CorrectionSummary(BaseModel):
    total: int
    by_source: list[CorrectionCount] = []
    confusions: list[Confusion] = []


class ModelStats(BaseModel):
    """What is labelling the data, and how sure it is.

    Deliberately does not include a single headline "accuracy": the training
    labels come from the keyword rules, so agreement with them measures
    imitation, not correctness. See s13a_model_stats for the full statement.
    """

    total_transactions: int
    by_source: list[SourceShare]
    confidence_buckets: list[ConfidenceBucket]
    abstentions: int
    confidence_threshold: float
    corrections: CorrectionSummary
    model_trained: bool
    model_path: str
    trainable_rows: int
    min_training_rows: int
    can_train: bool
    categories: int
    # Rows stored as 'rule' that no rule produced — see s13a_model_stats.
    # Counted as "nothing matched" above; reported here so the discrepancy
    # between the column and the truth is visible rather than hidden.
    stale_rule_rows: int = 0


class Correction(BaseModel):
    """One category change a user made."""

    id: int
    transaction_id: int
    date: dt.date
    merchant: str
    amount: Decimal
    from_category: str
    to_category: str
    from_source: str
    confidence_before: float | None = None
    corrected_at: dt.datetime

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class DataQualityIssue(BaseModel):
    """One check, and what it found.

    Returned even when `count` is zero — a clean check is a result, and a list
    that hides them cannot tell "checked, fine" from "never checked".
    """

    key: str
    severity: str
    title: str
    count: int
    detail: str
    note: str | None = None
    # The button label when a repair is safe to automate, null otherwise.
    fix_label: str | None = None


class DataQualityReport(BaseModel):
    total_transactions: int
    checks_run: int
    issues_found: int
    issues: list[DataQualityIssue]


class FixRequest(BaseModel):
    """Body of POST /api/data-quality/fix."""

    issue: str


class DataQualityFix(BaseModel):
    issue: str
    rows_changed: int


class AnswerRow(BaseModel):
    """One line of a list-shaped answer."""

    label: str
    value: str
    detail: str


class AnswerFilters(BaseModel):
    """The filters behind an answer, so the rows can be inspected."""

    month: str | None = None
    category: str | None = None
    direction: str | None = None


class Answer(BaseModel):
    """A parsed question and what it came to.

    `understood` false means the question did not match any shape this
    recognises — the parser matches keywords, it does not read language, and
    guessing would produce a confident answer to a different question.
    """

    understood: bool
    question: str
    # True when the question was understood but there is no statement to
    # answer it from. Distinct from `understood: false`, which means the
    # question itself could not be placed.
    no_data: bool = False
    reason: str | None = None
    examples: list[str] = []
    intent: str | None = None
    explanation: str | None = None
    answer: str | None = None
    value: Decimal | None = None
    rows: list[AnswerRow] = []
    filters: AnswerFilters | None = None

    @field_serializer("value")
    def serialize_value(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class AskRequest(BaseModel):
    """Body of POST /api/ask."""

    question: str


class RuleOut(BaseModel):
    """One of the user's own categorisation rules."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    category: str
    priority: int
    active: bool


class RuleCreate(BaseModel):
    """Body of POST /api/rules.

    `keyword` is matched as a case-insensitive substring, never as a regular
    expression — see s11a_rules for why that is deliberate.
    """

    keyword: str
    category: str
    priority: int = 100


class RuleUpdate(BaseModel):
    category: str | None = None
    priority: int | None = None
    active: bool | None = None


class RuleSample(BaseModel):
    """One transaction a rule would change."""

    id: int
    date: dt.date
    description: str
    merchant: str
    amount: Decimal
    current_category: str

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class RulePreview(BaseModel):
    """What a rule would do, before it does it."""

    keyword: str
    matches: int
    samples: list[RuleSample] = []


class RuleApplied(BaseModel):
    rule_id: int
    rows_changed: int


class AccountSummary(BaseModel):
    """One bank account, with how many transactions it holds.

    `id` is null for the "Unassigned" row — statements imported before
    accounts existed. It is a real bucket that can be filtered to, not a
    placeholder.
    """

    id: int | None = None
    name: str
    bank: str = ""
    last4: str = ""
    kind: str = "savings"
    transaction_count: int = 0


class AccountCreate(BaseModel):
    name: str
    bank: str = ""
    # Last four digits only. A full account number has no use in this app.
    last4: str = ""
    kind: str = "savings"


class AccountAssign(BaseModel):
    """Body and response of POST /api/accounts/assign."""

    upload_id: int
    account_id: int | None = None
    moved: int = 0


class AccountDeleted(BaseModel):
    account_id: int
    name: str
    transactions_unassigned: int


class ManualEntry(BaseModel):
    """Body of POST /api/manual.

    Only amount, date and direction are required. Recording Rs 100 should not
    mean filling a form.
    """

    amount: str
    date: dt.date
    # 'expense' or 'income' - the words the form uses. The sign is carried by
    # this choice, never by a minus in the amount.
    direction: str
    category: str | None = None
    merchant: str = ""
    payment_method: str = ""
    notes: str = ""
    account_id: int | None = None
    tags: list[str] = []


class ManualEntryUpdate(BaseModel):
    """Body of PATCH /api/manual/{id}. Every field optional."""

    amount: str | None = None
    date: dt.date | None = None
    direction: str | None = None
    category: str | None = None
    merchant: str | None = None
    payment_method: str | None = None
    notes: str | None = None
    account_id: int | None = None
    tags: list[str] | None = None


class CategorySuggestion(BaseModel):
    """What the existing rules make of a typed merchant name.

    `category` is null when nothing matched - an honest answer, and better
    than a guess the user would have to notice was wrong.
    """

    category: str | None = None
    label: str | None = None


class UserCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    label: str
    emoji: str = ""
    color: str = ""
    kind: str = "expense"
    parent_id: int | None = None
    archived: bool = False
    position: int = 100


class UserCategoryCreate(BaseModel):
    label: str
    emoji: str = ""
    color: str = ""
    kind: str = "expense"
    parent_id: int | None = None


class UserCategoryUpdate(BaseModel):
    label: str | None = None
    emoji: str | None = None
    color: str | None = None
    kind: str | None = None
    position: int | None = None
    archived: bool | None = None


class CategoryChoice(BaseModel):
    """Built-in and user categories in one list, as the pickers need them.

    A transaction form should not make the user care which half of the
    vocabulary a category came from.
    """

    category: str
    label: str
    emoji: str = ""
    color: str = ""
    kind: str = "expense"
    custom: bool = False
    archived: bool = False
    count: int = 0


class CategoryDeleted(BaseModel):
    deleted: bool
    label: str
    moved: int


class TagOut(BaseModel):
    id: int
    name: str
    count: int = 0


class TagCreate(BaseModel):
    name: str


class QuickExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: str = ""
    amount: Decimal
    direction: str
    category: str
    merchant_name: str = ""
    payment_method: str = ""
    account_id: int | None = None
    position: int = 100

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class QuickExpenseCreate(BaseModel):
    name: str
    amount: str
    category: str
    emoji: str = ""
    direction: str = "expense"
    merchant_name: str = ""
    payment_method: str = ""
    account_id: int | None = None


class ManualSummary(BaseModel):
    """The Personal Expenses page header.

    `available` false means nothing has been recorded by hand - which is a
    different statement from "you spent zero", and the page says so.
    """

    available: bool
    reason: str | None = None
    month: str | None = None
    today_total: Decimal | None = None
    month_total: Decimal | None = None
    month_income: Decimal | None = None
    average_daily: Decimal | None = None
    largest: Decimal | None = None
    total_count: int = 0
    month_count: int = 0

    @field_serializer(
        "today_total", "month_total", "month_income", "average_daily", "largest"
    )
    def serialize_money(self, amount: Decimal | None) -> str | None:
        return None if amount is None else f"{amount:.2f}"


class BudgetOut(BaseModel):
    """A limit the user set. Not a suggestion this app made."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    amount: Decimal
    active: bool = True

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class BudgetSet(BaseModel):
    """Body of POST /api/budgets. Upsert: one limit per category."""

    category: str
    amount: str


class BudgetUpdate(BaseModel):
    amount: str | None = None
    active: bool | None = None


class BudgetProgressItem(BaseModel):
    """One budget and how much of it has gone this month.

    `remaining` never goes negative — an overspend is reported as `over_by`
    instead, because "you have -900 left" is arithmetic rather than English.
    """

    id: int
    category: str
    label: str
    limit: Decimal
    spent: Decimal
    remaining: Decimal
    over_by: Decimal
    share: int
    # 'ok', 'near' or 'over'. Colour only — never a judgement about spending.
    state: str

    @field_serializer("limit", "spent", "remaining", "over_by")
    def serialize_money(self, amount: Decimal) -> str:
        return f"{amount:.2f}"


class BudgetProgress(BaseModel):
    """`available` false means no budget has been set — which is a different
    statement from every budget sitting at zero."""

    available: bool
    reason: str | None = None
    month: str
    days_left: int = 0
    total_limit: Decimal | None = None
    total_spent: Decimal | None = None
    total_remaining: Decimal | None = None
    over_count: int = 0
    budgets: list[BudgetProgressItem] = []

    @field_serializer("total_limit", "total_spent", "total_remaining")
    def serialize_money(self, amount: Decimal | None) -> str | None:
        return None if amount is None else f"{amount:.2f}"


class SettingsOut(BaseModel):
    """One user's preferences, with the options for each."""

    model_config = ConfigDict(from_attributes=True)

    anomaly_sensitivity: str = "medium"
    currency: str = "INR"
    date_format: str = "dmy"
    default_period: str = "all"


class SettingsUpdate(BaseModel):
    anomaly_sensitivity: str | None = None
    currency: str | None = None
    date_format: str | None = None
    default_period: str | None = None


class SettingsOptions(BaseModel):
    """What each setting may be set to, so the UI never hardcodes a list."""

    anomaly_sensitivity: list[str]
    currency: list[str]
    date_format: list[str]
    default_period: list[str]


class TransactionPage(BaseModel):
    """A page of transactions.

    `total` is the count matching the filters, not the length of `items` —
    the table needs it to show "showing 100 of 205".
    """

    total: int
    limit: int
    offset: int
    items: list[TransactionOut]
