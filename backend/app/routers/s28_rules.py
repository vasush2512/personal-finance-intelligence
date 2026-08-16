"""The user's own categorisation rules.

The built-in keyword rules ship with the app and cannot be edited by the person
using it. These can — and they win over the built-in ones, because a rule
someone wrote about their own bank's narrations is better evidence than a
general pattern.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import (
    RuleApplied,
    RuleCreate,
    RuleOut,
    RulePreview,
    RuleUpdate,
)
from app.store.s11a_rules import (
    RuleError,
    apply_rule,
    create_rule,
    delete_rule,
    list_rules,
    preview_rule,
    update_rule,
)

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut])
def get_rules(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """This user's rules, in the order they are applied."""
    return list_rules(session, user.id)


@router.post("", response_model=RuleOut, status_code=201)
def post_rule(
    body: RuleCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Add a rule. It applies to future imports; use /apply for existing rows."""
    try:
        return create_rule(
            session, user.id, body.keyword, body.category, body.priority
        )
    except RuleError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/preview", response_model=RulePreview)
def get_preview(
    keyword: str = Query(..., min_length=2, max_length=120),
    only_uncategorised: bool = Query(True),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """How many rows a keyword would change, and a few of them.

    Applying a rule across a hundred thousand transactions is not something to
    discover the effect of afterwards.
    """
    try:
        return preview_rule(session, user.id, keyword, only_uncategorised)
    except RuleError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.patch("/{rule_id}", response_model=RuleOut)
def patch_rule(
    rule_id: int,
    body: RuleUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    try:
        rule = update_rule(
            session, user.id, rule_id,
            category=body.category, priority=body.priority, active=body.active,
        )
    except RuleError as error:
        raise HTTPException(status_code=422, detail=str(error))

    if rule is None:
        raise HTTPException(status_code=404, detail="No such rule.")
    return rule


@router.post("/{rule_id}/apply", response_model=RuleApplied)
def post_apply(
    rule_id: int,
    only_uncategorised: bool = Query(True),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Run a stored rule over transactions already imported.

    Rows the user corrected by hand are never touched, whatever the flag says:
    a correction is the strongest evidence in the database and a rule written
    afterwards must not silently undo it.
    """
    changed = apply_rule(session, user.id, rule_id, only_uncategorised)
    return RuleApplied(rule_id=rule_id, rows_changed=changed)


@router.delete("/{rule_id}", status_code=204)
def remove_rule(
    rule_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Delete a rule. Categories it already applied are left as they are."""
    if not delete_rule(session, user.id, rule_id):
        raise HTTPException(status_code=404, detail="No such rule.")
    return None
