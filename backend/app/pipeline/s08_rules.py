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

from app.core.s01_constants import (
    KEYWORD_RULES,
    SOURCE_NONE,
    SOURCE_RULE,
    UNCATEGORIZED,
)

# Compile once at import; this runs on every imported row.
_COMPILED = [(re.compile(pattern, re.IGNORECASE), category)
             for pattern, category in KEYWORD_RULES]


def match_user_rules(normalized_description: str, user_rules):
    """The first user rule whose keyword appears, or None.

    `user_rules` is a list of (keyword, category) already in priority order.
    Matching is a plain case-insensitive substring test, not a regex: the
    keyword comes from a text box, and a regex box would let someone paste a
    pattern that takes exponential time to fail. "Contains BLINKIT" is also
    what people mean when they write a rule.
    """
    if not normalized_description or not user_rules:
        return None

    text = normalized_description.lower()
    for keyword, category in user_rules:
        if keyword and keyword.lower() in text:
            return category
    return None


def categorize_by_rules(normalized_description: str, user_rules=None):
    """Return a category name, or None when no rule matches.

    Expects the NORMALIZED description from services/normalize.py.

    The user's own rules are checked first and win. A rule someone wrote about
    their own bank's narrations is better evidence than a general pattern
    shipped with the app, and it should not be overruled by one.
    """
    if not normalized_description:
        return None

    from_user = match_user_rules(normalized_description, user_rules)
    if from_user is not None:
        return from_user

    for pattern, category in _COMPILED:
        if pattern.search(normalized_description):
            return category
    return None


def apply_rules(transactions, user_rules=None):
    """Tag a list of transaction dicts in place. Returns coverage stats.

    A row no rule matched is left as SOURCE_NONE, not SOURCE_RULE. Recording
    it as a rule label was the difference between "the rules recognised this"
    and "the rules ran over this", and only the first of those is worth
    reporting as coverage.

    The distinction also matters downstream: the model fills rows the rules
    left behind, so SOURCE_NONE is exactly the set of candidates it should
    look at, and whatever it still cannot place stays SOURCE_NONE afterwards.
    """
    matched = 0
    for txn in transactions:
        category = categorize_by_rules(txn["normalized_description"], user_rules)
        if category:
            txn["category"] = category
            txn["category_source"] = SOURCE_RULE
            txn["confidence"] = None
            matched += 1
        else:
            txn["category"] = UNCATEGORIZED
            txn["category_source"] = SOURCE_NONE
            txn["confidence"] = None

    total = len(transactions) or 1
    return {
        "total": len(transactions),
        "matched": matched,
        "coverage": round(matched / total, 3),
    }
