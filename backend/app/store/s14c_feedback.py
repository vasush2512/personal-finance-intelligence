"""Recording and reading the corrections a user makes to a category.

Writing this down is what turns a one-off fix into a signal. Without it the
only trace of a correction is category_source='user' on the row, which says
that somebody disagreed but not with whom, or how badly.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s04_models import CategoryFeedback, Transaction
from app.store.s12_aggregations import source_conditions

# How many recent corrections the Model page lists. Enough to recognise a
# pattern, few enough to read.
RECENT_LIMIT = 20


def record_correction(session: Session, transaction: Transaction, new_category: str):
    """Note that a label was changed, before the transaction is updated.

    Must be called while `transaction` still holds the OLD values — the point
    of the row is what the label used to be. Returns None when the category is
    unchanged, so re-saving the same value does not inflate the count.
    """
    if transaction.category == new_category:
        return None

    feedback = CategoryFeedback(
        transaction_id=transaction.id,
        from_category=transaction.category,
        to_category=new_category,
        from_source=transaction.category_source,
        confidence_before=transaction.confidence,
    )
    session.add(feedback)
    return feedback


def recent_corrections(session: Session, limit: int = RECENT_LIMIT, **source):
    """The latest corrections, newest first, with the row each refers to.

    Joined to the transaction so the list can show what was actually
    corrected — "food to groceries" means little without the merchant.
    """
    rows = session.execute(
        select(CategoryFeedback, Transaction)
        .join(Transaction, Transaction.id == CategoryFeedback.transaction_id)
        .where(*source_conditions(**source))
        .order_by(CategoryFeedback.corrected_at.desc(), CategoryFeedback.id.desc())
        .limit(limit)
    ).all()

    return [
        {
            "id": feedback.id,
            "transaction_id": feedback.transaction_id,
            "date": transaction.date,
            "merchant": transaction.merchant,
            "amount": transaction.amount,
            "from_category": feedback.from_category,
            "to_category": feedback.to_category,
            "from_source": feedback.from_source,
            "confidence_before": feedback.confidence_before,
            "corrected_at": feedback.corrected_at,
        }
        for feedback, transaction in rows
    ]
