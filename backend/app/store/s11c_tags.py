"""User-defined tags, and which transactions carry them.

Categories answer *what kind of spending is this*. Tags answer *what was this
for*. A Delhi trip is not a category — it is food and transport and shopping
that happen to share a context, and forcing it into the category vocabulary
would corrupt every category total it touched.

Kept deliberately small: a name, an owner, and a join table. Tags do not
affect a single figure anywhere in the app. They are for finding things again.
"""

import re

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.s04_models import Tag, Transaction, TransactionTag

MAX_TAGS = 100

# Enough per transaction to describe a context; few enough that the row still
# renders. Nobody needs twelve tags on one coffee.
MAX_TAGS_PER_TRANSACTION = 8

_CLEAN = re.compile(r"[^a-z0-9\- ]+")


class TagError(ValueError):
    """A tag operation that cannot proceed, with a readable reason."""


def clean_name(raw: str) -> str:
    """'#Delhi Trip!' -> 'delhi trip'.

    Lowercased and stripped of punctuation so that #Delhi, #delhi and
    "Delhi " are one tag rather than three that look identical in a list.
    """
    name = _CLEAN.sub("", str(raw or "").strip().lstrip("#").lower())
    name = " ".join(name.split())

    if len(name) < 2:
        raise TagError("A tag needs at least two characters.")
    if len(name) > 30:
        raise TagError("That tag is too long.")
    return name


def list_tags(session: Session, user_id: int):
    """This user's tags, with how many transactions carry each."""
    counts = dict(
        session.execute(
            select(TransactionTag.tag_id, func.count(TransactionTag.id))
            .join(Tag, Tag.id == TransactionTag.tag_id)
            .where(Tag.user_id == user_id)
            .group_by(TransactionTag.tag_id)
        ).all()
    )

    rows = session.execute(
        select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)
    ).scalars().all()

    return [
        {"id": row.id, "name": row.name, "count": counts.get(row.id, 0)}
        for row in rows
    ]


def get_or_create(session: Session, user_id: int, name: str) -> Tag:
    """Find a tag by name or make it. Typing a tag is how tags get created."""
    name = clean_name(name)

    existing = session.execute(
        select(Tag).where(Tag.user_id == user_id, Tag.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    total = session.execute(
        select(func.count(Tag.id)).where(Tag.user_id == user_id)
    ).scalar_one()
    if total >= MAX_TAGS:
        raise TagError(f"That is more than {MAX_TAGS} tags.")

    tag = Tag(user_id=user_id, name=name)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


def set_tags(session: Session, user_id: int, transaction_id: int, names):
    """Replace a transaction's tags with exactly this set.

    Replace rather than append: the UI edits the whole set at once, and an
    append-only API would make removing a tag impossible without a second
    call that could half-fail.
    """
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user_id:
        return None

    wanted = []
    for name in (names or []):
        cleaned = clean_name(name)
        if cleaned not in wanted:
            wanted.append(cleaned)

    if len(wanted) > MAX_TAGS_PER_TRANSACTION:
        raise TagError(
            f"That is more than {MAX_TAGS_PER_TRANSACTION} tags on one "
            f"transaction."
        )

    session.execute(
        delete(TransactionTag).where(TransactionTag.transaction_id == transaction_id)
    )

    for name in wanted:
        tag = get_or_create(session, user_id, name)
        session.add(TransactionTag(transaction_id=transaction_id, tag_id=tag.id))

    session.commit()
    return wanted


def tags_for(session: Session, user_id: int, transaction_id: int):
    """The tag names on one transaction."""
    return session.execute(
        select(Tag.name)
        .join(TransactionTag, TransactionTag.tag_id == Tag.id)
        .where(
            TransactionTag.transaction_id == transaction_id,
            Tag.user_id == user_id,
        )
        .order_by(Tag.name)
    ).scalars().all()


def tags_for_many(session: Session, user_id: int, transaction_ids):
    """{transaction_id: [names]} for a page of rows, in one query.

    The list endpoint returns a hundred transactions; asking per row would be
    a hundred queries to decorate one table.
    """
    if not transaction_ids:
        return {}

    rows = session.execute(
        select(TransactionTag.transaction_id, Tag.name)
        .join(Tag, Tag.id == TransactionTag.tag_id)
        .where(
            TransactionTag.transaction_id.in_(list(transaction_ids)),
            Tag.user_id == user_id,
        )
        .order_by(Tag.name)
    ).all()

    grouped: dict[int, list[str]] = {}
    for transaction_id, name in rows:
        grouped.setdefault(transaction_id, []).append(name)
    return grouped


def transaction_ids_with_tag(session: Session, user_id: int, name: str):
    """Every transaction carrying a tag, for the filter."""
    return session.execute(
        select(TransactionTag.transaction_id)
        .join(Tag, Tag.id == TransactionTag.tag_id)
        .where(Tag.user_id == user_id, Tag.name == clean_name(name))
    ).scalars().all()


def delete_tag(session: Session, user_id: int, tag_id: int) -> bool:
    """Remove a tag and detach it everywhere. Transactions are untouched."""
    tag = session.get(Tag, tag_id)
    if tag is None or tag.user_id != user_id:
        return False

    session.execute(delete(TransactionTag).where(TransactionTag.tag_id == tag_id))
    session.delete(tag)
    session.commit()
    return True
