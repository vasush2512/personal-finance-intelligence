"""The user's own categories, alongside the built-in vocabulary.

The built-in list in constants.py is deliberately fixed: the keyword rules,
the trained model and every analytics function are written against it, and
letting a user edit it would change what those mean. So a user's categories
sit beside it rather than inside it, and a transaction can carry either.

Three rules this module exists to enforce:

  - **A key is generated once and never changes.** Renaming "Gym" to
    "Fitness" edits the label; the key stays `u_gym` and the thousand
    transactions pointing at it are untouched. Display names are not database
    keys, and a rename must not be able to orphan history.
  - **A category in use cannot be deleted.** It can be archived, or its
    transactions can be moved somewhere else first. Silently dropping the
    category off a year of spending is not a delete, it is data loss with a
    confirmation dialog in front of it.
  - **Everything is scoped to one user.** One person's categories are never
    visible, editable or countable by another.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.s01_constants import (
    CATEGORIES,
    UNCATEGORIZED,
    USER_CATEGORY_PREFIX,
    is_user_category,
)
from app.core.s04_models import Transaction, UserCategory

# Enough for anyone organising their own spending; low enough that the
# category picker stays a list a person can read.
MAX_CATEGORIES = 60

_SLUG = re.compile(r"[^a-z0-9]+")


class CategoryError(ValueError):
    """A category operation that cannot proceed, with a readable reason."""


def _make_key(label: str) -> str:
    """'Delhi Trip' -> 'u_delhi_trip'. Generated once, then permanent."""
    slug = _SLUG.sub("_", label.strip().lower()).strip("_")
    if not slug:
        raise CategoryError("Give the category a name using letters or numbers.")
    return f"{USER_CATEGORY_PREFIX}{slug}"[:48]


def _clean_label(label: str) -> str:
    label = " ".join(str(label or "").split())
    if len(label) < 2:
        raise CategoryError("A category name needs at least two characters.")
    if len(label) > 40:
        raise CategoryError("That category name is too long.")
    return label


def list_categories(session: Session, user_id: int, include_archived: bool = False):
    """This user's categories, in display order."""
    conditions = [UserCategory.user_id == user_id]
    if not include_archived:
        conditions.append(UserCategory.archived.is_(False))

    return session.execute(
        select(UserCategory)
        .where(*conditions)
        .order_by(UserCategory.position, UserCategory.id)
    ).scalars().all()


def valid_categories(session: Session, user_id: int) -> set[str]:
    """Every category key this user may put on a transaction.

    The built-in vocabulary plus their own, archived ones included: a row
    already carrying an archived category must still be editable and savable
    without being forced onto a different category.
    """
    own = session.execute(
        select(UserCategory.key).where(UserCategory.user_id == user_id)
    ).scalars().all()
    return set(CATEGORIES) | set(own)


def ensure_valid(session: Session, user_id: int, category: str) -> str:
    """Check a category belongs to this user or to the built-in list."""
    if category in valid_categories(session, user_id):
        return category

    raise CategoryError(
        f"Unknown category {category!r}. Choose a built-in category or one of "
        f"your own."
    )


def usage_counts(session: Session, user_id: int) -> dict[str, int]:
    """How many transactions carry each category, for this user."""
    rows = session.execute(
        select(Transaction.category, func.count(Transaction.id))
        .where(Transaction.user_id == user_id)
        .group_by(Transaction.category)
    ).all()
    return dict(rows)


def create_category(session: Session, user_id: int, label: str, emoji: str = "",
                    color: str = "", kind: str = "expense", parent_id=None):
    label = _clean_label(label)
    key = _make_key(label)

    if key in CATEGORIES or key.removeprefix(USER_CATEGORY_PREFIX) in CATEGORIES:
        raise CategoryError(
            f"{label!r} already exists as a built-in category — use that one."
        )

    existing = session.execute(
        select(UserCategory).where(
            UserCategory.user_id == user_id, UserCategory.key == key
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CategoryError(
            f"You already have a category called {existing.label!r}."
            + (" It is archived — restore it instead." if existing.archived else "")
        )

    if len(list_categories(session, user_id, include_archived=True)) >= MAX_CATEGORIES:
        raise CategoryError(f"That is more than {MAX_CATEGORIES} categories.")

    if parent_id is not None:
        parent = session.get(UserCategory, parent_id)
        if parent is None or parent.user_id != user_id:
            raise CategoryError("That parent category does not exist.")

    category = UserCategory(
        user_id=user_id,
        key=key,
        label=label,
        emoji=(emoji or "")[:8],
        color=(color or "")[:9],
        kind="income" if str(kind).lower() == "income" else "expense",
        parent_id=parent_id,
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def update_category(session: Session, user_id: int, category_id: int, **changes):
    """Rename or restyle. The key is never touched — see the module docstring."""
    category = session.get(UserCategory, category_id)
    if category is None or category.user_id != user_id:
        return None

    if changes.get("label") is not None:
        category.label = _clean_label(changes["label"])
    for field in ("emoji", "color"):
        if changes.get(field) is not None:
            setattr(category, field, changes[field][:9])
    if changes.get("kind") is not None:
        category.kind = "income" if str(changes["kind"]).lower() == "income" else "expense"
    if changes.get("position") is not None:
        category.position = int(changes["position"])
    if changes.get("archived") is not None:
        category.archived = bool(changes["archived"])

    session.commit()
    session.refresh(category)
    return category


def delete_category(session: Session, user_id: int, category_id: int,
                    move_to: str | None = None):
    """Delete a category, moving or refusing if transactions still use it.

    Returns {"deleted": True, "moved": n} on success. Raises CategoryError
    describing the blockage when transactions would be left pointing at a
    category that no longer exists.
    """
    category = session.get(UserCategory, category_id)
    if category is None or category.user_id != user_id:
        return None

    in_use = session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id, Transaction.category == category.key
        )
    ).scalar_one()

    if in_use and move_to is None:
        raise CategoryError(
            f"{category.label!r} is used by {in_use:,} transactions. Archive it "
            f"instead, or choose a category to move those transactions to — "
            f"deleting it would leave them pointing at a category that no "
            f"longer exists."
        )

    moved = 0
    if in_use:
        if move_to == category.key:
            raise CategoryError("Choose a different category to move them to.")
        ensure_valid(session, user_id, move_to)

        for row in session.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.category == category.key,
            )
        ).scalars():
            row.category = move_to
            moved += 1

    # Children would otherwise point at a parent that is gone.
    for child in session.execute(
        select(UserCategory).where(UserCategory.parent_id == category.id)
    ).scalars():
        child.parent_id = None

    label = category.label
    session.delete(category)
    session.commit()
    return {"deleted": True, "label": label, "moved": moved}


def category_options(session: Session, user_id: int):
    """Built-in and user categories together, as the pickers need them.

    One list, because a transaction form should not make the user care which
    half of the vocabulary a category came from.
    """
    counts = usage_counts(session, user_id)

    options = [
        {
            "category": key,
            "label": _builtin_label(key),
            "emoji": "",
            "color": "",
            "kind": "income" if key == "income" else "expense",
            "custom": False,
            "archived": False,
            "count": counts.get(key, 0),
        }
        for key in CATEGORIES
    ]

    options += [
        {
            "category": row.key,
            "label": row.label,
            "emoji": row.emoji,
            "color": row.color,
            "kind": row.kind,
            "custom": True,
            "archived": row.archived,
            "count": counts.get(row.key, 0),
        }
        for row in list_categories(session, user_id, include_archived=True)
    ]

    return options


def _builtin_label(key: str) -> str:
    if key == "bills_utilities":
        return "Bills & utilities"
    if key == UNCATEGORIZED:
        return "Other"
    return key.replace("_", " ").capitalize()


def label_for(session: Session, user_id: int, key: str) -> str:
    """A display name for any category key, built-in or the user's own."""
    if not is_user_category(key):
        return _builtin_label(key)

    row = session.execute(
        select(UserCategory).where(
            UserCategory.user_id == user_id, UserCategory.key == key
        )
    ).scalar_one_or_none()
    return row.label if row else key
