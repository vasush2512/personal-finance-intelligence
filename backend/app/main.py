"""FastAPI application entry point.

Run from backend/:  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import create_all
from app.routers import model, transactions, uploads

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


app.include_router(uploads.router)
app.include_router(transactions.router)
app.include_router(model.router)


@app.get("/health")
def health():
    """Liveness check. Also the quickest way to confirm startup worked."""
    return {"status": "ok"}
