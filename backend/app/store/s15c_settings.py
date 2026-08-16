"""Per-user preferences.

Every setting has a default, and the row is created on first read rather than
at sign-up. An account that has never opened the Settings page therefore
behaves exactly as it did before this existed — which is what makes adding
this safe for a database full of existing users.

Only one of these changes behaviour rather than presentation: anomaly
sensitivity moves the threshold the unusual-spending detector uses. The rest
are about how figures are written down.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s04_models import UserSettings
from app.pipeline.s10_anomalies import SENSITIVITY

SENSITIVITIES = list(SENSITIVITY)
CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"]
DATE_FORMATS = ["dmy", "mdy", "iso"]
PERIODS = ["all", "month"]


class SettingsError(ValueError):
    """A setting that cannot be stored, with a readable reason."""


def get_settings(session: Session, user_id: int) -> UserSettings:
    """This user's settings, created with defaults the first time they are read.

    Created lazily on purpose: back-filling a row for every existing account
    would be writing data to record that nobody has chosen anything yet, which
    the absence of the row already says.
    """
    settings = session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    ).scalar_one_or_none()

    if settings is None:
        settings = UserSettings(user_id=user_id)
        session.add(settings)
        session.commit()
        session.refresh(settings)

    return settings


def update_settings(session: Session, user_id: int, **changes) -> UserSettings:
    """Change one or more preferences. Unknown values are refused, not coerced."""
    settings = get_settings(session, user_id)

    checks = {
        "anomaly_sensitivity": (SENSITIVITIES, "sensitivity"),
        "currency": (CURRENCIES, "currency"),
        "date_format": (DATE_FORMATS, "date format"),
        "default_period": (PERIODS, "period"),
    }

    for field, (allowed, noun) in checks.items():
        value = changes.get(field)
        if value is None:
            continue
        if value not in allowed:
            raise SettingsError(
                f"Unknown {noun} {value!r}. Choose one of: {', '.join(allowed)}."
            )
        setattr(settings, field, value)

    settings.updated_at = dt.datetime.now()
    session.commit()
    session.refresh(settings)
    return settings


def sensitivity_for(session: Session, user_id: int) -> str:
    """Just the anomaly setting, for the detector's callers."""
    return get_settings(session, user_id).anomaly_sensitivity
