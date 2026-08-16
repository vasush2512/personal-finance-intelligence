"""The user's own categorisation rules: storing them, and applying them.

The built-in keyword rules cover common Indian merchants and still leave a lot
uncategorised on real data — nearly half, in the case that prompted this. The
person using the app cannot edit constants.py, so this lets them write rules of
their own.

Two things that make this safe to hand to a user:

  - **A keyword, not a regex.** Matched as a case-insensitive substring. A
    regex box would be more powerful and would also accept a pattern that takes
    exponential time to fail, pasted from anywhere.
  - **Applying a rule never overwrites a correction.** A row the user has
    already categorised by hand is the strongest evidence in the database, and
    a rule written later must not silently undo it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s01_constants import CATEGORIES, SOURCE_RULE, SOURCE_USER
from app.core.s04_models import CategoryRule, Transaction
from app.store.s12_aggregations import source_conditions

# A ceiling on rules per user. Every rule is tested against every row on
# import, so an unbounded list is an unbounded import time.
MAX_RULES = 200


class RuleError(ValueError):
    """A rule that cannot be stored, with a message worth showing."""


def _clean_keyword(keyword: str) -> str:
    cleaned = (keyword or "").strip()
    if len(cleaned) < 2:
        raise RuleError(
            "A keyword needs at least two characters — a single letter would "
            "match almost every transaction you have."
        )
    if len(cleaned) > 120:
        raise RuleError("That keyword is too long to be a keyword.")
    return cleaned


def list_rules(session: Session, user_id: int):
    """This user's rules, in the order they are applied."""
    return session.execute(
        select(CategoryRule)
        .where(CategoryRule.user_id == user_id)
        .order_by(CategoryRule.priority, CategoryRule.id)
    ).scalars().all()


def active_pairs(session: Session, user_id: int):
    """(keyword, category) in priority order — what the matcher consumes.

    Kept separate from `list_rules` because the import path wants the pairs and
    nothing else, and should not carry ORM objects into a pure function.
    """
    return [
        (rule.keyword, rule.category)
        for rule in list_rules(session, user_id)
        if rule.active
    ]


def create_rule(session: Session, user_id: int, keyword: str, category: str,
                priority: int = 100):
    """Add a rule. Raises RuleError with something worth reading."""
    keyword = _clean_keyword(keyword)

    if category not in CATEGORIES:
        raise RuleError(
            f"Unknown category {category!r}. Valid: {', '.join(CATEGORIES)}"
        )

    existing = session.execute(
        select(CategoryRule).where(
            CategoryRule.user_id == user_id,
            CategoryRule.keyword == keyword,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise RuleError(
            f"You already have a rule for {keyword!r} — it sends those "
            f"transactions to {existing.category}. Edit or delete that one."
        )

    if len(list_rules(session, user_id)) >= MAX_RULES:
        raise RuleError(
            f"That is more than {MAX_RULES} rules. Every rule is checked "
            f"against every row on import, so the list has to stop somewhere."
        )

    rule = CategoryRule(
        user_id=user_id, keyword=keyword, category=category, priority=priority
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def update_rule(session: Session, user_id: int, rule_id: int, **changes):
    """Change a rule's category, priority or active flag."""
    rule = session.get(CategoryRule, rule_id)
    if rule is None or rule.user_id != user_id:
        return None

    if "category" in changes and changes["category"] is not None:
        if changes["category"] not in CATEGORIES:
            raise RuleError(f"Unknown category {changes['category']!r}.")
        rule.category = changes["category"]

    if changes.get("priority") is not None:
        rule.priority = changes["priority"]

    if changes.get("active") is not None:
        rule.active = changes["active"]

    session.commit()
    session.refresh(rule)
    return rule


def delete_rule(session: Session, user_id: int, rule_id: int) -> bool:
    """Remove a rule. Categories it already applied are left alone.

    Deleting a rule does not un-categorise what it matched: those rows were
    labelled, the labels are still correct as far as anyone knows, and silently
    reverting thousands of them would be a much bigger surprise than leaving
    them.
    """
    rule = session.get(CategoryRule, rule_id)
    if rule is None or rule.user_id != user_id:
        return False

    session.delete(rule)
    session.commit()
    return True


def _matching_rows(session: Session, user_id: int, keyword: str, only_uncategorised: bool):
    """Rows a keyword would match, honouring the never-overwrite rules."""
    conditions = [
        *source_conditions(user_id=user_id),
        Transaction.normalized_description.ilike(f"%{keyword.lower()}%"),
        # A hand-made correction outranks any rule written afterwards.
        Transaction.category_source != SOURCE_USER,
    ]

    if only_uncategorised:
        # The common case: fill the gaps without touching what already worked.
        conditions.append(Transaction.category_source != SOURCE_RULE)

    return conditions


def preview_rule(session: Session, user_id: int, keyword: str,
                 only_uncategorised: bool = True):
    """How many rows a rule would change, and a few of them, before it runs.

    Applying a rule to a hundred thousand transactions is not something to
    discover the effect of afterwards.
    """
    keyword = _clean_keyword(keyword)
    conditions = _matching_rows(session, user_id, keyword, only_uncategorised)

    rows = session.execute(
        select(Transaction).where(*conditions).limit(5)
    ).scalars().all()

    total = session.execute(
        select(Transaction.id).where(*conditions)
    ).scalars().all()

    return {
        "keyword": keyword,
        "matches": len(total),
        "samples": [
            {
                "id": row.id,
                "date": row.date,
                "description": row.description,
                "merchant": row.merchant,
                "amount": row.amount,
                "current_category": row.category,
            }
            for row in rows
        ],
    }


def apply_rule(session: Session, user_id: int, rule_id: int,
               only_uncategorised: bool = True) -> int:
    """Apply one stored rule to existing transactions. Returns rows changed.

    Marked SOURCE_RULE, not SOURCE_USER: a rule is a rule, even a hand-written
    one, and calling it a personal correction would inflate the count of
    genuine corrections the Model page reports.
    """
    rule = session.get(CategoryRule, rule_id)
    if rule is None or rule.user_id != user_id:
        return 0

    conditions = _matching_rows(session, user_id, rule.keyword, only_uncategorised)
    rows = session.execute(select(Transaction).where(*conditions)).scalars().all()

    for row in rows:
        row.category = rule.category
        row.category_source = SOURCE_RULE
        # A rule matched it; whatever the model once thought is no longer what
        # this row's label is based on.
        row.confidence = None

    session.commit()
    return len(rows)
