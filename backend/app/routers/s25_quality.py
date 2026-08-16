"""Data quality checks, and the one repair that is safe to automate."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import DataQualityFix, DataQualityReport, FixRequest
from app.store.s12c_quality import apply_fix, data_quality

router = APIRouter(prefix="/api", tags=["quality"])


@router.get("/data-quality", response_model=DataQualityReport)
def get_data_quality(
    upload_id: int | None = Query(None, description="restrict to one statement"),
    sheet: str | None = Query(None),
    account_id: int | None = Query(None),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Everything wrong, missing or odd about the imported rows.

    Checks that found nothing are returned too, with a count of zero — a list
    that only shows problems cannot distinguish "checked, fine" from "never
    checked".
    """
    return data_quality(
        session, user_id=user.id, upload_id=upload_id, sheet=sheet,
        account_id=account_id,
        entry_source=entry_source,
    )


@router.post("/data-quality/fix", response_model=DataQualityFix)
def fix_data_quality(
    body: FixRequest,
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(None),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Apply one repair, by key.

    Only 'stale_rule_source' is accepted. It rewrites a label column that is
    provably wrong and touches nothing else — not the category, not the amount,
    not the date. Every other issue on that page needs either a human decision
    or a corrected file, and this endpoint refuses rather than pretending
    otherwise.
    """
    try:
        # Fixes the rows the report was describing, not every row the
        # user owns — the two must not be able to disagree.
        changed = apply_fix(
            session, body.issue, user_id=user.id, upload_id=upload_id,
            sheet=sheet, account_id=account_id, entry_source=entry_source,
        )
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"There is no automatic fix for {body.issue!r}. Only "
                f"'stale_rule_source' can be corrected automatically."
            ),
        )

    return DataQualityFix(issue=body.issue, rows_changed=changed)
