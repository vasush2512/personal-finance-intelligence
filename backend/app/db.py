"""Database engine, session factory, and the declarative Base."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL, ensure_data_dir


class Base(DeclarativeBase):
    """Parent class for every model in models.py."""


# check_same_thread=False: FastAPI serves requests from a thread pool, and the
# default SQLite driver refuses to reuse a connection across threads.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _connection_record):
    """Turn on foreign key enforcement.

    SQLite ignores foreign keys unless this pragma is set on every connection.
    Without it the ON DELETE CASCADE on transactions.upload_id would silently
    do nothing and deleting an upload would leave its rows orphaned.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session():
    """FastAPI dependency. Yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Create data/ and any missing tables. Called on startup."""
    ensure_data_dir()
    Base.metadata.create_all(bind=engine)
