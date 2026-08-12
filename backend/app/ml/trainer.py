"""Stage 2 of categorization: the learned classifier.

Interview notes — be able to explain all four of these:

1. WHY TRAIN ON RULE OUTPUT?
   The rules produce the initial labels (weak supervision). The model then
   generalizes beyond the exact keywords: it learns that a narration
   resembling other food rows is food, even for a restaurant no rule names.
   User corrections are added to the same training set, so the model improves
   every time the user fixes a row.

2. WHY WORD *AND* CHARACTER N-GRAMS?
   Bank narrations glue tokens together ("UPISWIGGYBLR", "AMAZONPAYINDIA").
   Word n-grams miss those entirely. Character n-grams (char_wb, 3-5) catch
   the substring "swigg" regardless of what it is fused to. Combining both
   with FeatureUnion is what makes this work on real data.

3. WHY LOGISTIC REGRESSION AND NOT SOMETHING BIGGER?
   The feature space is high-dimensional and sparse and the dataset is small
   (hundreds of rows). Linear models are the right tool there: fast, hard to
   overfit with regularization, and inspectable — you can read the top
   weighted n-grams per class and explain a prediction.

4. WHY A CONFIDENCE THRESHOLD?
   A wrong category the user has to hunt down is worse than an honest
   "other". Below 0.55 predicted probability we abstain.
"""

import os

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from app.constants import UNCATEGORIZED

MIN_TRAINING_ROWS = 50
CONFIDENCE_THRESHOLD = 0.55
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "model.joblib")


class NotEnoughData(Exception):
    """Raised when there are too few labelled rows to train honestly."""


def build_pipeline():
    word_features = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    char_features = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        sublinear_tf=True,
        min_df=2,
    )
    return Pipeline(
        [
            ("features", FeatureUnion([("word", word_features), ("char", char_features)])),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    C=4.0,
                    class_weight="balanced",
                ),
            ),
        ]
    )


def collect_training_data(transactions):
    """Rule-labelled and user-labelled rows only. 'other' is not a label."""
    texts, labels = [], []
    for txn in transactions:
        category = txn.get("category")
        source = txn.get("category_source")
        if source in ("rule", "user") and category and category != UNCATEGORIZED:
            texts.append(txn["normalized_description"])
            labels.append(category)
    return texts, labels


def train(transactions, model_path=MODEL_PATH):
    """Train, evaluate on a held-out split, persist. Returns a report dict."""
    texts, labels = collect_training_data(transactions)

    if len(texts) < MIN_TRAINING_ROWS:
        raise NotEnoughData(
            f"Only {len(texts)} labelled rows; need at least {MIN_TRAINING_ROWS}. "
            "Upload more statements or correct some categories first."
        )

    # Classes with a single example cannot be stratified or evaluated.
    counts = {label: labels.count(label) for label in set(labels)}
    usable = [(t, l) for t, l in zip(texts, labels) if counts[l] >= 2]
    texts, labels = [t for t, _ in usable], [l for _, l in usable]

    stratify = labels if min(counts[l] for l in set(labels)) >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.25, random_state=42, stratify=stratify
    )

    pipeline = build_pipeline()
    pipeline.fit(x_train, y_train)
    accuracy = pipeline.score(x_test, y_test)

    # Refit on everything before saving — the split was only for the estimate.
    pipeline.fit(texts, labels)
    os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
    joblib.dump(pipeline, model_path)

    return {
        "trained": True,
        "labelled_rows": len(texts),
        "classes": sorted(set(labels)),
        "holdout_accuracy": round(float(accuracy), 3),
        "model_path": os.path.abspath(model_path),
    }


def load_model(model_path=MODEL_PATH):
    if not os.path.exists(model_path):
        return None
    return joblib.load(model_path)


def predict(model, normalized_description):
    """Return (category, confidence). Abstains below the threshold."""
    if model is None or not normalized_description:
        return UNCATEGORIZED, None

    probabilities = model.predict_proba([normalized_description])[0]
    best_index = probabilities.argmax()
    confidence = float(probabilities[best_index])
    category = model.classes_[best_index]

    if confidence < CONFIDENCE_THRESHOLD:
        return UNCATEGORIZED, round(confidence, 3)
    return category, round(confidence, 3)


def categorize_unmatched(transactions, model):
    """Fill in rows the rules could not label. Never touches user labels."""
    filled = 0
    for txn in transactions:
        if txn.get("category_source") == "user":
            continue
        if txn.get("category") not in (None, UNCATEGORIZED):
            continue

        category, confidence = predict(model, txn["normalized_description"])
        txn["confidence"] = confidence
        if category != UNCATEGORIZED:
            txn["category"] = category
            txn["category_source"] = "model"
            filled += 1
    return filled
