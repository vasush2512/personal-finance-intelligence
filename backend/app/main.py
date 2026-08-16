"""FastAPI application entry point.

Run from backend/:  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.s02_config import FRONTEND_ORIGIN
from app.core.s03_db import create_all
from app.routers import (
    s17_uploads,
    s18_transactions,
    s19_analytics,
    s20_model,
    s21_anomalies,
    s22_auth,
    s23_patterns,
    s24_intelligence,
    s25_quality,
    s26_export,
    s27_ask,
    s28_rules,
    s29_accounts,
    s30_manual,
    s31_taxonomy,
    s32_budgets,
    s33_settings,
)

# Imported for the side effect of registering the models on Base.metadata,
# so create_all() actually sees them.
from app.core import s04_models as models  # noqa: F401


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create data/ and any missing tables before the first request."""
    create_all()
    yield


app = FastAPI(
    title="Expense Tracker API",
    version="0.1.0",
    lifespan=lifespan,
)


# The Vite dev server runs on a different port, which makes every request
# from it cross-origin. Localhost only — this app is never deployed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registered in reading order, which is also roughly the order a user meets
# them: upload a file, look at the rows, fix a category, retrain, see the
# dashboard, see what was unusual.
app.include_router(s17_uploads.router)
app.include_router(s18_transactions.router)
app.include_router(s19_analytics.router)
app.include_router(s20_model.router)
app.include_router(s21_anomalies.router)
app.include_router(s22_auth.router)
app.include_router(s23_patterns.router)
app.include_router(s24_intelligence.router)
app.include_router(s25_quality.router)
app.include_router(s26_export.router)
app.include_router(s27_ask.router)
app.include_router(s28_rules.router)
app.include_router(s29_accounts.router)
app.include_router(s30_manual.router)
app.include_router(s31_taxonomy.router)
app.include_router(s32_budgets.router)
app.include_router(s33_settings.router)


@app.get("/health")
def health():
    """Liveness check. Also the quickest way to confirm startup worked."""
    return {"status": "ok"}
