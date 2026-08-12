"""Stage 1 of categorization: keyword rules.

Why rules first, before any machine learning?

On day one there is no training data. A classifier needs labelled examples
and nobody wants to hand-label 200 transactions before the app does anything
useful. So the rules do two jobs:

  1. They categorize the obvious merchants immediately (Swiggy -> food).
  2. Their output becomes the training set for the model, which then
     generalizes to merchants no rule covers.

Every rule-labelled row is later used by trainer.py. This is weak supervision:
cheap, noisy labels bootstrapping a real model.
"""

import re

from app.constants import KEYWORD_RULES, UNCATEGORIZED

# Compile once at import; this runs on every imported row.
_COMPILED = [(re.compile(pattern, re.IGNORECASE), category)
             for pattern, category in KEYWORD_RULES]


def categorize_by_rules(normalized_description: str):
    """Return a category name, or None when no rule matches.

    Expects the NORMALIZED description from services/normalize.py.
    """
    if not normalized_description:
        return None
    for pattern, category in _COMPILED:
        if pattern.search(normalized_description):
            return category
    return None


def apply_rules(transactions):
    """Tag a list of transaction dicts in place. Returns coverage stats."""
    matched = 0
    for txn in transactions:
        category = categorize_by_rules(txn["normalized_description"])
        if category:
            txn["category"] = category
            txn["category_source"] = "rule"
            txn["confidence"] = None
            matched += 1
        else:
            txn["category"] = UNCATEGORIZED
            txn["category_source"] = "rule"
            txn["confidence"] = None

    total = len(transactions) or 1
    return {
        "total": len(transactions),
        "matched": matched,
        "coverage": round(matched / total, 3),
    }
