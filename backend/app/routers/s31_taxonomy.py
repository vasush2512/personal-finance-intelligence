"""The user's own categories and tags.

Both are vocabulary rather than data: they describe transactions without being
transactions. Grouped in one router for that reason, and kept separate from
/api/categories, which returns the built-in list and must keep doing exactly
that for every existing caller.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import (
    CategoryChoice,
    CategoryDeleted,
    TagCreate,
    TagOut,
    UserCategoryCreate,
    UserCategoryOut,
    UserCategoryUpdate,
)
from app.store.s11b_categories import (
    CategoryError,
    category_options,
    create_category,
    delete_category,
    list_categories,
    update_category,
)
from app.store.s11c_tags import TagError, delete_tag, get_or_create, list_tags

router = APIRouter(prefix="/api", tags=["taxonomy"])


@router.get("/category-choices", response_model=list[CategoryChoice])
def get_category_choices(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Built-in and custom categories in one list, with usage counts.

    A separate endpoint from /api/categories rather than a change to it: that
    one is consumed by the transactions table, the filters and the model page,
    and widening its shape would mean touching all three to add a field only
    the entry form needs.
    """
    return category_options(session, user.id)


@router.get("/user-categories", response_model=list[UserCategoryOut])
def get_user_categories(
    include_archived: bool = Query(False),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Only the categories this user created."""
    return list_categories(session, user.id, include_archived=include_archived)


@router.post("/user-categories", response_model=UserCategoryOut, status_code=201)
def post_user_category(
    body: UserCategoryCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    try:
        return create_category(
            session, user.id, body.label, emoji=body.emoji, color=body.color,
            kind=body.kind, parent_id=body.parent_id,
        )
    except CategoryError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.patch("/user-categories/{category_id}", response_model=UserCategoryOut)
def patch_user_category(
    category_id: int,
    body: UserCategoryUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Rename, restyle, reorder or archive.

    The key is never changed, so no transaction moves. Renaming "Gym" to
    "Fitness" is a label edit, not a migration.
    """
    try:
        category = update_category(
            session, user.id, category_id, **body.model_dump()
        )
    except CategoryError as error:
        raise HTTPException(status_code=422, detail=str(error))

    if category is None:
        raise HTTPException(status_code=404, detail="No such category.")
    return category


@router.delete("/user-categories/{category_id}", response_model=CategoryDeleted)
def remove_user_category(
    category_id: int,
    move_to: str | None = Query(
        None, description="category to move existing transactions to"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Delete a category.

    422 with a count when transactions still use it and no destination was
    given — deleting it would leave them pointing at something that no longer
    exists. Archive it, or pass move_to.
    """
    try:
        result = delete_category(session, user.id, category_id, move_to=move_to)
    except CategoryError as error:
        raise HTTPException(status_code=422, detail=str(error))

    if result is None:
        raise HTTPException(status_code=404, detail="No such category.")
    return CategoryDeleted(**result)


# --- tags ------------------------------------------------------------------


@router.get("/tags", response_model=list[TagOut])
def get_tags(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """This user's tags, with how many transactions carry each."""
    return list_tags(session, user.id)


@router.post("/tags", response_model=TagOut, status_code=201)
def post_tag(
    body: TagCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Create a tag explicitly. Typing one on a transaction also creates it."""
    try:
        tag = get_or_create(session, user.id, body.name)
    except TagError as error:
        raise HTTPException(status_code=422, detail=str(error))

    return TagOut(id=tag.id, name=tag.name, count=0)


@router.delete("/tags/{tag_id}", status_code=204)
def remove_tag(
    tag_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Delete a tag and detach it everywhere. No transaction is affected."""
    if not delete_tag(session, user.id, tag_id):
        raise HTTPException(status_code=404, detail="No such tag.")
    return None
