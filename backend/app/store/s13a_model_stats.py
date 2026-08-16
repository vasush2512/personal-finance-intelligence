"""What is actually labelling the data, and how sure it is.

The Model page used to report one number: holdout accuracy from the last
retrain. That number is agreement with the keyword rules, because the rules
produced the training labels — it measures whether the classifier learned to
imitate the rules, not whether either of them is right. Shown alone, next to
the word "accuracy", it reads as a claim this project cannot make.

So this assembles the figures that are honest instead: how many rows each
labeller accounts for, how confident the model was when it did label something,
and how often a person had to come back and change it.
"""

import os

from sqlalchemy import func, select

from app.core.s01_constants import (
    CATEGORIES,
    SOURCE_MODEL,
    SOURCE_NONE,
    SOURCE_RULE,
    SOURCE_USER,
    UNCATEGORIZED,
)
from app.core.s02_config import MODEL_PATH
from app.core.s04_models import CategoryFeedback, Transaction
from app.pipeline.s09_model import CONFIDENCE_THRESHOLD, MIN_TRAINING_ROWS
from app.store.s12_aggregations import source_conditions

# Where the confidence histogram is cut. The threshold itself is a boundary,
# so it gets its own edge rather than falling inside a wider bucket.
_BUCKETS = [
    ("Very high", 0.90, 1.01),
    ("High", 0.75, 0.90),
    ("Moderate", CONFIDENCE_THRESHOLD, 0.75),
]

_SOURCE_LABELS = {
    SOURCE_RULE: "Keyword rules",
    SOURCE_MODEL: "Classifier",
    SOURCE_USER: "You corrected it",
    SOURCE_NONE: "Nothing matched",
}


def _stale_rule_rows(session, **source):
    """Rows stored as 'rule' that no rule can have produced.

    Before the source vocabulary gained 'none', every imported row defaulted to
    category_source='rule' whether a rule had matched it or not. Those rows are
    still in the database, and counting them as rule coverage is how this page
    came to report that the keyword rules cover 100% of the data while also
    reporting fifty thousand abstentions — two figures that cannot both be true.

    No keyword rule targets the fallback category, so 'rule' plus
    UNCATEGORIZED is decisive: nothing matched. Counted here and reported as
    such, rather than fixed by an UPDATE nobody asked for.
    """
    return session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.category_source == SOURCE_RULE,
            Transaction.category == UNCATEGORIZED,
            *source_conditions(**source),
        )
    ).scalar_one()


def _counts_by_source(session, **source):
    rows = session.execute(
        select(Transaction.category_source, func.count(Transaction.id))
        .where(*source_conditions(**source))
        .group_by(Transaction.category_source)
    ).all()
    counts = {name: count for name, count in rows}

    # Report where the label actually came from, not what the column says.
    stale = _stale_rule_rows(session, **source)
    if stale:
        counts[SOURCE_RULE] = counts.get(SOURCE_RULE, 0) - stale
        counts[SOURCE_NONE] = counts.get(SOURCE_NONE, 0) + stale

    return counts, stale


def _confidence_buckets(session, **source):
    """How sure the classifier was, for the rows it labelled.

    Only model-labelled rows have a confidence worth reporting: a rule either
    matched or did not, and a person is not a probability.
    """
    buckets = []
    for label, low, high in _BUCKETS:
        count = session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.category_source == SOURCE_MODEL,
                Transaction.confidence >= low,
                Transaction.confidence < high,
                *source_conditions(**source),
            )
        ).scalar_one()
        buckets.append({
            "label": label,
            "low": round(low, 2),
            "high": round(min(high, 1.0), 2),
            "count": count,
        })
    return buckets


def _abstentions(session, **source):
    """Rows the model looked at and declined to label.

    An abstention is the model working correctly, not failing — below the
    threshold it says nothing rather than guessing. Counting these as errors
    is how a coverage figure starts flattering itself.
    """
    return session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.category == UNCATEGORIZED,
            Transaction.confidence.isnot(None),
            *source_conditions(**source),
        )
    ).scalar_one()


def _corrections(session):
    """What the user has changed, and what it says about each labeller.

    Not filtered by source: a correction is a fact about the model, and
    scoping it to one uploaded file would make the figure move every time the
    filter did.
    """
    total = session.execute(
        select(func.count(CategoryFeedback.id))
    ).scalar_one()

    by_source = dict(session.execute(
        select(CategoryFeedback.from_source, func.count(CategoryFeedback.id))
        .group_by(CategoryFeedback.from_source)
    ).all())

    # Which wrong answer, corrected to what. The pairs a classifier confuses
    # are far more useful than a single accuracy number.
    confusions = session.execute(
        select(
            CategoryFeedback.from_category,
            CategoryFeedback.to_category,
            func.count(CategoryFeedback.id).label("count"),
        )
        .where(CategoryFeedback.from_source == SOURCE_MODEL)
        .group_by(CategoryFeedback.from_category, CategoryFeedback.to_category)
        .order_by(func.count(CategoryFeedback.id).desc())
        .limit(8)
    ).all()

    return {
        "total": total,
        "by_source": [
            {
                "source": name,
                "label": _SOURCE_LABELS.get(name, name),
                "count": count,
            }
            for name, count in sorted(by_source.items(), key=lambda item: -item[1])
        ],
        "confusions": [
            {
                "from_category": from_category,
                "to_category": to_category,
                "count": count,
            }
            for from_category, to_category, count in confusions
        ],
    }


def model_stats(session, **source):
    """Everything the Model page shows, in one call."""
    counts, stale = _counts_by_source(session, **source)
    total = sum(counts.values())

    trainable = counts.get(SOURCE_RULE, 0) + counts.get(SOURCE_USER, 0)

    return {
        "total_transactions": total,
        "by_source": [
            {
                "source": name,
                "label": _SOURCE_LABELS[name],
                "count": counts.get(name, 0),
                "share": (
                    round(counts.get(name, 0) / total * 100, 1) if total else 0.0
                ),
            }
            # A fixed order, so the bars do not reshuffle between reloads.
            for name in (SOURCE_RULE, SOURCE_MODEL, SOURCE_USER, SOURCE_NONE)
        ],
        "confidence_buckets": _confidence_buckets(session, **source),
        "abstentions": _abstentions(session, **source),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "corrections": _corrections(session),
        "model_trained": os.path.exists(MODEL_PATH),
        "model_path": str(MODEL_PATH),
        "trainable_rows": trainable,
        "min_training_rows": MIN_TRAINING_ROWS,
        "can_train": trainable >= MIN_TRAINING_ROWS,
        "categories": len(CATEGORIES),
        # Surfaced rather than silently corrected: the rows are counted
        # honestly above, but the column they are stored in still says 'rule',
        # and whoever reads this page should know that.
        "stale_rule_rows": stale,
    }
