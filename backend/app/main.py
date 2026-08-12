"""FastAPI application entry point.

Run from backend/:  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import FRONTEND_ORIGIN
from app.db import create_all
from app.routers import analytics, model, transactions, uploads

# Imported for the side effect of registering the models on Base.metadata,
# so create_all() actually sees them.
from app import models  # noqa: F401


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

app.include_router(uploads.router)
app.include_router(transactions.router)
app.include_router(model.router)
app.include_router(analytics.router)


@app.get("/health")
def health():
    """Liveness check. Also the quickest way to confirm startup worked."""
    return {"status": "ok"}
