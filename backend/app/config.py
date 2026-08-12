"""Settings and filesystem paths.

Every path in the app is derived from BASE_DIR, so the app behaves the same
whether it is started from backend/ or from the project root.
"""

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
