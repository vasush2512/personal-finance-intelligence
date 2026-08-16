"""Per-user preferences.

One of these changes behaviour rather than presentation: anomaly sensitivity
moves the threshold the unusual-spending detector uses, so /api/anomalies and
the financial health score both read it. The rest describe how figures should
be written down.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.s16_schemas import SettingsOptions, SettingsOut, SettingsUpdate
from app.store.s15c_settings import (
    CURRENCIES,
    DATE_FORMATS,
    PERIODS,
    SENSITIVITIES,
    SettingsError,
    get_settings,
    update_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """This user's preferences, with defaults the first time they are read."""
    return get_settings(session, user.id)


@router.get("/options", response_model=SettingsOptions)
def read_options(user: User = Depends(current_user)):
    """What each setting may be set to.

    Served rather than hardcoded in the frontend so the two cannot drift —
    the same reason /api/categories exists.
    """
    return SettingsOptions(
        anomaly_sensitivity=SENSITIVITIES,
        currency=CURRENCIES,
        date_format=DATE_FORMATS,
        default_period=PERIODS,
    )


@router.patch("", response_model=SettingsOut)
def patch_settings(
    body: SettingsUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Change one or more preferences. An unknown value is refused, not coerced."""
    try:
        return update_settings(session, user.id, **body.model_dump())
    except SettingsError as error:
        raise HTTPException(status_code=422, detail=str(error))
