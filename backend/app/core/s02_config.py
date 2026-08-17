"""Settings and filesystem paths.

Every path in the app is derived from BASE_DIR, so the app behaves the same
whether it is started from backend/ or from the project root.
"""

import os
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
def normalize_database_url(url: str) -> str:
    """Point PostgreSQL URLs at the driver that is actually installed.

    We install psycopg 3. SQLAlchemy resolves a bare `postgresql://` to
    psycopg *2* — a different package, absent here — so the URL a host hands
    out fails with `ModuleNotFoundError: No module named 'psycopg2'`, which
    reads like a missing dependency rather than the scheme mismatch it is.
    `postgres://` is worse: SQLAlchemy 2.x dropped that alias outright.

    Rewriting the scheme is the entire fix, and doing it here means the value
    can be wired straight through from the host — including render.yaml's
    `fromDatabase`, which offers no opportunity to edit it by hand.

    Anything else, SQLite included, is returned untouched.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return f"postgresql+psycopg://{url[len(prefix):]}"
    return url


# The SQLite file is the default, not the only option. A host that provides a
# managed database sets DATABASE_URL and the app follows it — which is the
# difference between a demo whose data is wiped on every deploy and one that
# keeps it. DATABASE_PATH above stays meaningful either way: it is still where
# a local run puts its file.
DATABASE_URL = normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        f"sqlite:///{DATABASE_PATH}",
    )
)

SAMPLE_STATEMENT_PATH = DATA_DIR / "sample_statement.csv"

# Note: app/ml/trainer.py currently computes its own model path. Phase 4 should
# make it read this one instead, so there is a single source of truth.
MODEL_PATH = DATA_DIR / "model.joblib"

# Vite's dev server. Used by the CORS middleware in Phase 5.
FRONTEND_ORIGIN = "http://localhost:5173"

# Both spellings of the dev server. A browser treats "localhost" and
# "127.0.0.1" as different origins even though they are the same machine, so
# omitting either one breaks whichever address the developer happened to type.
LOCAL_ORIGINS = [FRONTEND_ORIGIN, "http://127.0.0.1:5173"]


def parse_origins(raw: str | None) -> list[str]:
    """Split an ALLOWED_ORIGINS value into origins the CORS middleware accepts.

    Kept as a plain function so it can be tested without setting environment
    variables. Blank entries are dropped and trailing slashes are stripped:
    the Origin header a browser sends never has a trailing slash, so
    "https://app.vercel.app/" pasted from the address bar would silently match
    nothing and look like a server fault rather than a typo.
    """
    if not raw:
        return []
    origins = []
    for entry in raw.split(","):
        origin = entry.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins


# Deployed frontends, supplied by the host as a comma-separated list. The dev
# origins stay in the list unconditionally so a deployed backend can still be
# pointed at from a laptop while debugging.
ALLOWED_ORIGINS = LOCAL_ORIGINS + [
    origin
    for origin in parse_origins(os.getenv("ALLOWED_ORIGINS"))
    if origin not in LOCAL_ORIGINS
]

# Vercel gives every preview build its own hostname, so the production URL
# alone would block every preview. Set this to something like
# r"https://.*\.vercel\.app" to allow them. Left unset by default: a regex is
# a wider door than a list, and it should be opened deliberately.
ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX") or None


def ensure_data_dir() -> None:
    """Create data/ if it does not exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
