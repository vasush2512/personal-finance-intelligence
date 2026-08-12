"""Database side of the classifier.

app/ml/trainer.py knows about scikit-learn and nothing about SQLAlchemy.
This module is the bridge: it reads labelled rows out of the database, hands
them to the trainer, and reports back. Route handlers call this, never the
trainer directly.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MODEL_PATH
from app.ml.trainer import train
from app.models import Transaction


def labelled_rows(session: Session):
    """Every stored row, as the plain dicts the trainer expects.

    The trainer decides what counts as trainable (rule- and user-labelled,
    never 'other'), so nothing is filtered here.
    """
    rows = session.execute(select(Transaction)).scalars().all()
    return [
        {
            "normalized_description": row.normalized_description,
            "category": row.category,
            "category_source": row.category_source,
        }
        for row in rows
    ]


def retrain(session: Session, model_path=None) -> dict:
    """Fit the classifier on what is in the database and save it.

    Raises NotEnoughData (from trainer.py) when there are too few labelled
    rows to train honestly. The caller turns that into a 400.
    """
    path = str(model_path or MODEL_PATH)
    return train(labelled_rows(session), model_path=path)
