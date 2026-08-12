"""SQLAlchemy models — PRD 6.

Two tables: uploads (one row per CSV the user submits) and transactions
(one row per parsed line). Deleting an upload deletes its transactions.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import UNCATEGORIZED
from app.db import Base

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


class Upload(Base):
    """One uploaded CSV file, with the counts we reported back to the user."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"), index=True
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
    # 'rule', 'model', or 'user'. A 'user' row is never overwritten.
    category_source: Mapped[str] = mapped_column(String(8), default="rule")
    # Model probability. Null for rule-labelled and user-corrected rows.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # SHA-256 of date|normalized_description|amount|direction (PRD 7.2).
    # The unique index is what makes re-uploading a statement a no-op.
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    upload: Mapped["Upload | None"] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction {self.date} {self.description[:30]!r} "
            f"{self.direction} {self.amount} {self.category}>"
        )
