"""Settings and filesystem paths.

Every path in the app is derived from BASE_DIR, so the app behaves the same
whether it is started from backend/ or from the project root.
"""

from pathlib import Path

# backend/  —  this file is backend/app/core/s02_config.py, so the walk up is
# core -> app -> backend.
#
# Anchored on a landmark rather than a fixed number of parents. Counting levels
# broke silently the moment this module moved from app/ into app/core/: the two
# hops that used to land on backend/ landed on app/, so the app quietly created
# and used an empty backend/app/data/expenses.db while the real database sat
# untouched. Nothing failed — it just talked to the wrong file.
#
# Searching upward for the directory that holds data/ cannot drift that way,
# and raises loudly if the layout ever changes beyond recognition.
def _find_backend_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        # requirements.txt, not data/. A stray data/ directory is exactly what
        # this bug produces, so using it as the landmark would let the wrong
        # answer confirm itself.
        if (candidate / "requirements.txt").is_file():
            return candidate
    # Fall back to the historical layout rather than crashing on import.
    return here.parents[2]


BASE_DIR = _find_backend_root()

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
