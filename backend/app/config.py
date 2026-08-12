"""Settings and filesystem paths.

Every path in the app is derived from BASE_DIR, so the app behaves the same
whether it is started from backend/ or from the project root.
"""

import configparser
import os
from pathlib import Path

# backend/  (this file is backend/app/config.py)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "expenses.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

SAMPLE_STATEMENT_PATH = DATA_DIR / "sample_statement.csv"

# Note: app/ml/trainer.py currently computes its own model path. Phase 4 should
# make it read this one instead, so there is a single source of truth.
MODEL_PATH = DATA_DIR / "model.joblib"

# Vite's dev server. Used by the CORS middleware in Phase 5.
FRONTEND_ORIGIN = "http://localhost:5173"


def ensure_data_dir() -> None:
    """Create data/ if it does not exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# --- SMS credentials ------------------------------------------------------

# Read from backend/sms.ini, which is gitignored. Environment variables win
# over the file, so a deployment can set them without shipping a file at all.
SMS_CONFIG_PATH = BASE_DIR / "sms.ini"

SMS_KEYS = (
    "provider",
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_from",
    "msg91_authkey",
    "msg91_template_id",
    "fast2sms_api_key",
)


def sms_settings() -> dict:
    """Whatever SMS credentials are configured, or an empty-ish default.

    Read fresh each time rather than cached at import: editing sms.ini and
    restarting is one step, and a cached blank would look like the file was
    ignored.

    Nothing here is ever logged or returned by the API. A leaked auth token
    is somebody else's phone bill.
    """
    settings = {"provider": "console"}

    if SMS_CONFIG_PATH.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(SMS_CONFIG_PATH, encoding="utf-8")
            if parser.has_section("sms"):
                settings.update(
                    {key: value.strip() for key, value in parser.items("sms") if value.strip()}
                )
        except configparser.Error:
            # A malformed file must not stop the app from starting; it just
            # means no SMS, which is the default anyway.
            pass

    for key in SMS_KEYS:
        from_env = os.environ.get(f"SMS_{key.upper()}")
        if from_env:
            settings[key] = from_env.strip()

    return settings
