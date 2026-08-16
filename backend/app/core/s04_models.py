"""SQLAlchemy models — PRD 6.

Three tables: uploads (one row per file the user submits), transactions
(one row per parsed line), and users (one row per registered account).
Deleting an upload deletes its transactions.

Every transaction and upload belongs to a user, and every query filters on
that — see s16a_auth.owned(). This was not always true: the API used to ask
nobody who was calling, and a comment here said so. It does now, and a request
without a live row in `sessions` cannot read anything.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.s01_constants import SOURCE_NONE, UNCATEGORIZED
from app.core.s03_db import Base

PAISE_PER_RUPEE = 100
TWO_PLACES = Decimal("0.01")


class Money(TypeDecorator):
    """Decimal rupees in Python, integer paise in the database.

    Why not just use Numeric(12, 2)? SQLite has no decimal type. Handed a
    Numeric column, SQLAlchemy stores the value as a float and converts back
    on the way out — it even warns that rounding errors may occur. That
    breaks the project's rule that money is never a float.

    Storing whole paise as an integer keeps arithmetic exact, lets SQL do
    SUM() and ORDER BY correctly, and still hands Python a Decimal. The
    trade-off is that the raw column reads as 45000, not 450.00.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Decimal('450.00') -> 45000"""
        if value is None:
            return None
        rupees = Decimal(str(value)).quantize(TWO_PLACES)
        return int(rupees * PAISE_PER_RUPEE)

    def process_result_value(self, value, dialect):
        """45000 -> Decimal('450.00')"""
        if value is None:
            return None
        return (Decimal(value) / PAISE_PER_RUPEE).quantize(TWO_PLACES)


class User(Base):
    """One registered account.

    The password itself is never stored — only the output of a slow salted
    hash, in the format services/accounts.py documents. Nothing in the API
    ever returns password_hash.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stored already lowercased and trimmed by accounts.normalize_email, so
    # the unique constraint below actually means "one account per address".
    # Without that, Guru@x.com and guru@x.com would be two accounts.
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)

    display_name: Mapped[str] = mapped_column(String(60), default="")

    # 'pbkdf2_sha256$600000$<salt>$<hash>'. The parameters travel with the
    # hash so the iteration count can be raised later without locking
    # everybody out of their existing password.
    password_hash: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    last_signed_in_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email!r}>"


class DuplicateVerdict(Base):
    """What the user decided about a suggested duplicate pair.

    Detection is recomputed on every request — the rule depends on a moving
    window, so a stored flag would go stale exactly like a stored anomaly flag
    would. What must persist is the human's answer, because re-asking about a
    pair someone has already dismissed is how a useful panel becomes noise.

    Keyed on the pair, lowest id first, so the same two transactions always
    produce the same row whichever order they were compared in.
    """

    __tablename__ = "duplicate_verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)

    first_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    second_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )

    # True = the user confirmed these are one payment recorded twice.
    # False = the user said they are genuinely two transactions.
    is_duplicate: Mapped[bool] = mapped_column(Boolean)

    decided_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("first_id", "second_id", name="uq_duplicate_pair"),
    )

    def __repr__(self) -> str:
        return (
            f"<DuplicateVerdict {self.first_id}+{self.second_id} "
            f"duplicate={self.is_duplicate}>"
        )


class Account(Base):
    """One bank account the user uploads statements for.

    Without this, two banks' statements merge into one undifferentiated pile:
    a salary credit in HDFC and a card payment in SBI land in the same totals
    with nothing saying they came from different places. Uploads point at an
    account, so the whole app can be filtered to one — or left across all.

    The number is stored already masked. A full account number has no use
    anywhere in this app, so there is no reason to hold one.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # What the user calls it: "HDFC Salary", "SBI Joint".
    name: Mapped[str] = mapped_column(String(60))
    bank: Mapped[str] = mapped_column(String(60), default="")

    # Last four digits only, and only if the user typed them. Never the whole
    # number — see the docstring.
    last4: Mapped[str] = mapped_column(String(4), default="")

    # savings / current / credit card. Free text rather than an enum: the
    # vocabulary of account types is longer than any list worth maintaining.
    kind: Mapped[str] = mapped_column(String(20), default="savings")

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Account {self.id} {self.name!r}>"


class UserCategory(Base):
    """A category the user defined, alongside the built-in vocabulary.

    `key` is what a transaction stores, and it is generated from the label
    once and then never changes. Renaming "Gym" to "Fitness" edits `label`
    and leaves `key` alone, so a thousand transactions do not have to be
    rewritten and none of them can be orphaned by a rename. Display names are
    not database keys.

    Deletion is refused while transactions still point at a category — see
    s11b_categories for the archive-or-move flow that replaces it.
    """

    __tablename__ = "user_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Stable, lowercase, never edited after creation. Prefixed so a user
    # category can never collide with a built-in one.
    key: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(48))

    # Optional decoration. An emoji rather than an icon name: the icon set is
    # hand-drawn SVG and cannot be extended by a user at runtime.
    emoji: Mapped[str] = mapped_column(String(8), default="")
    color: Mapped[str] = mapped_column(String(9), default="")

    # 'expense' or 'income'. Used to offer the right categories on the right
    # form, never to decide what a transaction actually is — direction does
    # that, as it always has.
    kind: Mapped[str] = mapped_column(String(8), default="expense")

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_categories.id", ondelete="SET NULL"), nullable=True
    )

    # Archived categories stop being offered on forms but keep working for
    # every transaction already using them.
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=100)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_category_per_user"),
    )

    def __repr__(self) -> str:
        return f"<UserCategory {self.key!r} {self.label!r}>"


class Tag(Base):
    """A user-defined label that is not a category.

    Categories answer "what kind of spending is this"; tags answer "what was
    this for". A Delhi trip is not a category — it is food and transport and
    shopping that happen to share a context, and forcing it into the category
    vocabulary would break every category total it touched.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_per_user"),)

    def __repr__(self) -> str:
        return f"<Tag {self.name!r}>"


class TransactionTag(Base):
    """Which tags are on which transaction. Many-to-many, nothing more."""

    __tablename__ = "transaction_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), index=True
    )

    __table_args__ = (
        UniqueConstraint("transaction_id", "tag_id", name="uq_transaction_tag"),
    )


class UserSettings(Base):
    """One row per user: how they want the app to behave and read.

    Deliberately a single row rather than a key/value table. There are a
    handful of settings, they all have types, and a typed column that cannot
    hold nonsense is worth more here than a schema that never needs migrating.

    Every column has a default, and the row is created on first read, so an
    account that has never opened Settings behaves exactly as before.
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # 'low' | 'medium' | 'high'. Changes the standard-deviation threshold the
    # unusual-spending detector uses — see SENSITIVITY in s10_anomalies. It is
    # a preference about how much noise is useful, not a measure of accuracy.
    anomaly_sensitivity: Mapped[str] = mapped_column(String(8), default="medium")

    # Display only. Amounts are stored in paise and are not converted by this;
    # changing it relabels the figures rather than reinterpreting them, which
    # the Settings page says out loud.
    currency: Mapped[str] = mapped_column(String(8), default="INR")

    # 'dmy' | 'mdy' | 'iso'.
    date_format: Mapped[str] = mapped_column(String(8), default="dmy")

    # Whether the dashboard opens on everything or on this month.
    default_period: Mapped[str] = mapped_column(String(12), default="all")

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<UserSettings user={self.user_id} {self.anomaly_sensitivity}>"


class Budget(Base):
    """A monthly spending limit the user set for one category.

    A budget is a target somebody chose, not a recommendation this app made.
    Nothing here is derived, suggested or adjusted automatically — the number
    is whatever they typed, and the only thing computed is how much of it has
    been spent.

    Monthly only, deliberately. Weekly and yearly budgets are a different
    question about a different period, and supporting all three would mean
    every figure on the page having to say which one it meant.

    One per category: two budgets for Food would have to be reconciled, and
    there is no honest way to do that.
    """

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # A category key — built-in or one of the user's own. Never a display
    # name, for the same reason transactions store keys.
    category: Mapped[str] = mapped_column(String(48), index=True)

    # The limit for one calendar month.
    amount: Mapped[Decimal] = mapped_column(Money)

    # Turned off rather than deleted, so a budget can be paused for a month
    # without losing the figure that was chosen.
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_budget_per_category"),
    )

    def __repr__(self) -> str:
        return f"<Budget {self.category} {self.amount}>"


class QuickExpense(Base):
    """A one-click template for an expense the user records often.

    A template is not a transaction and never becomes one on its own. Pressing
    it creates a real transaction dated today; until then it is only a saved
    set of defaults. Nothing about it appears in any total.
    """

    __tablename__ = "quick_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(40))
    emoji: Mapped[str] = mapped_column(String(8), default="")
    amount: Mapped[Decimal] = mapped_column(Money)
    direction: Mapped[str] = mapped_column(String(6), default="debit")
    category: Mapped[str] = mapped_column(String(48))
    merchant_name: Mapped[str] = mapped_column(String(80), default="")
    payment_method: Mapped[str] = mapped_column(String(20), default="")
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<QuickExpense {self.name!r} {self.amount}>"


class CategoryRule(Base):
    """A rule the user wrote, matching a keyword to a category.

    The built-in keyword rules in constants.py cover common Indian merchants,
    and on real data they still leave a lot uncategorised — nearly half, in the
    case that prompted this. Editing constants.py is not something the person
    using the app can do.

    So: their own rules, stored per user, applied before the built-in ones and
    winning over them. A rule someone wrote about their own bank's narrations
    is better evidence than a general pattern, and it should not be overruled
    by one.

    `keyword` is matched as a case-insensitive substring, not a regular
    expression. A regex box would be more powerful and would also let someone
    paste a pattern that takes exponential time to fail — and "contains
    BLINKIT" is what people actually want to say.
    """

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    keyword: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(32))

    # Lower runs first, so a specific rule can be placed above a general one.
    priority: Mapped[int] = mapped_column(Integer, default=100)

    # Turned off rather than deleted, so a rule can be tested without losing
    # the wording of it.
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "keyword", name="uq_rule_per_user"),
    )

    def __repr__(self) -> str:
        return f"<CategoryRule {self.keyword!r} -> {self.category}>"


class Session(Base):
    """One signed-in session, identified by a token the browser holds.

    Sign-in used to be entirely cosmetic: the browser remembered an account and
    no endpoint ever asked who was calling. This table is what makes it real —
    a request without a live row here cannot read anybody's transactions.

    Only the *hash* of the token is stored. A stolen database file then yields
    no usable sessions, for the same reason it yields no usable passwords.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # sha256 of the token. Unique, so a lookup is an index hit rather than a
    # scan over every live session.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    # Checked on every request. A session that outlives its expiry is a
    # password that never changes.
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)

    def __repr__(self) -> str:
        return f"<Session user={self.user_id} expires={self.expires_at}>"


class CategoryFeedback(Base):
    """One correction a user made to a category.

    The transaction itself already carries the answer — category and
    category_source='user'. What it cannot carry is the *history*: what the
    label was before, who had assigned it, and how sure the model had been.
    That is the part worth keeping, because it is the only honest measure of
    whether the classifier is getting better or worse.

    Deliberately append-only. Correcting the same row twice writes a second
    row rather than overwriting the first: a correction that was itself
    corrected is a fact about the model, not a mistake to erase.
    """

    __tablename__ = "category_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )

    from_category: Mapped[str] = mapped_column(String(32))
    to_category: Mapped[str] = mapped_column(String(32), index=True)

    # Who had assigned the label being replaced — one of CATEGORY_SOURCES.
    # This is what separates "the model got it wrong" from "no rule matched".
    from_source: Mapped[str] = mapped_column(String(8))

    # How sure the model had been, when it was the model. Null otherwise.
    # A high-confidence correction is a much worse sign than a low-confidence
    # one, and the difference is invisible without this.
    confidence_before: Mapped[float | None] = mapped_column(Float, nullable=True)

    corrected_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<CategoryFeedback {self.transaction_id} "
            f"{self.from_category}->{self.to_category} was={self.from_source}>"
        )


class Upload(Base):
    """One uploaded CSV file, with the counts we reported back to the user."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Who uploaded this file. Nullable only so the column could be added to an
    # existing database without rewriting it; every new row sets it, and the
    # backfill in scripts/backfill_ownership.py assigns the historical ones.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )

    # Which bank account this statement came from. Nullable: statements
    # imported before accounts existed have none, and the app treats that as
    # "unassigned" rather than refusing to show them.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), index=True, nullable=True
    )

    filename: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    rows_parsed: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Upload {self.id} {self.filename!r} imported={self.rows_imported}>"


class Transaction(Base):
    """One parsed statement line.

    Field names match what services/parser.py already produces, so an import
    is a straight dict-to-model copy.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Whose transaction this is. Every query that returns financial data
    # filters on it — see s16a_auth.owned(). Nullable for the same
    # add-a-column reason as Upload.user_id above.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )

    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"), index=True
    )

    # Copied from the upload rather than joined. Every filtered query in the
    # app would otherwise need a join to uploads purely to answer "which
    # bank?", and this is the filter people reach for most.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Which worksheet this row came from, for workbooks with a tab per month.
    # Null for CSV and JSON, which hold a single table.
    sheet_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    date: Mapped[dt.date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String)
    normalized_description: Mapped[str] = mapped_column(String, default="")

    # Always positive. direction carries the sign.
    amount: Mapped[Decimal] = mapped_column(Money)
    direction: Mapped[str] = mapped_column(String(6))

    # Category names come from constants.py only — never a literal here.
    category: Mapped[str] = mapped_column(
        String(32), default=UNCATEGORIZED, index=True
    )
    # One of CATEGORY_SOURCES. A 'user' row is never overwritten.
    #
    # Defaults to 'none' rather than 'rule': a row inserted without anyone
    # saying who labelled it has not been labelled by the rules, and claiming
    # otherwise is how the coverage figure came to count its own misses.
    category_source: Mapped[str] = mapped_column(String(8), default=SOURCE_NONE)
    # Model probability. Null for rule-labelled and user-corrected rows.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # How this row entered the system: ENTRY_STATEMENT or ENTRY_MANUAL.
    # Nullable, and NULL is read as "statement" — every row that existed
    # before manual entry was possible came from a statement, and backfilling
    # a hundred thousand rows to say so would change data to record something
    # already known from its absence.
    entry_source: Mapped[str | None] = mapped_column(
        String(12), index=True, nullable=True
    )

    # Typed by the user on a manual entry. Statement rows leave this null and
    # keep deriving the merchant from the narration — see the merchant
    # property below.
    merchant_name: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Chosen on a manual entry. Statement rows leave this null and keep
    # deriving it from the narration, which is the only place it exists there.
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # The user's own note. Never parsed, never matched against, never shown
    # to the categoriser — it is for the person, not the pipeline.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Set when a manual row is edited. Null on rows that have never been
    # edited, which is most of them.
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # SHA-256 of date|normalized_description|amount|direction (PRD 7.2).
    # The unique index is what makes re-uploading a statement a no-op.
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    upload: Mapped["Upload | None"] = relationship(back_populates="transactions")

    @property
    def merchant(self) -> str:
        """A displayable merchant name, derived rather than stored.

        A property, not a column: the inputs are already on the row, so a
        column would be a second copy that could fall out of step with the
        narration it came from — and adding one means backfilling every
        existing row before the UI can trust it.

        Pydantic reads this like any other attribute (from_attributes), so it
        costs nothing at query time and appears in the API for free.
        """
        # Imported here rather than at module scope: models is imported by
        # db.py during table creation, and a top-level import would drag the
        # normalizer into that path for no reason.
        # A manual entry has no bank narration to read, and the name the user
        # typed is better evidence than anything that could be extracted from
        # it. Statement rows are unaffected: they leave merchant_name null.
        if self.merchant_name:
            return self.merchant_name

        from app.pipeline.s05_normalize import extract_merchant

        return extract_merchant(self.description, self.normalized_description)

    def __repr__(self) -> str:
        return (
            f"<Transaction {self.date} {self.description[:30]!r} "
            f"{self.direction} {self.amount} {self.category}>"
        )
