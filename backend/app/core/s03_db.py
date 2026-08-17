"""Database engine, session factory, and the declarative Base."""

import sqlite3

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.s02_config import DATABASE_URL, ensure_data_dir


class Base(DeclarativeBase):
    """Parent class for every model in models.py."""


# check_same_thread is a SQLite driver argument and nothing else understands
# it, so passing it to PostgreSQL raises TypeError before the first query.
#
# SQLite needs it because FastAPI serves requests from a thread pool and the
# default driver refuses to reuse a connection across threads. A PostgreSQL
# driver has no such restriction, and SQLAlchemy's connection pool already
# does the right thing there, so the plain call is correct.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)


@event.listens_for(Engine, "connect")
def _enable_foreign_keys(dbapi_connection, _connection_record):
    """Turn on foreign key enforcement for every SQLite connection.

    SQLite ignores foreign keys unless this pragma is set, per connection.
    Without it the ON DELETE CASCADE on transactions.upload_id silently does
    nothing and deleting an upload leaves its rows orphaned.

    This listens on the Engine *class*, not on our one engine, so that test
    engines behave identically to the real one. Attaching it to a single
    engine is what let this bug through the first time.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
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
    add_missing_columns()


def add_missing_columns() -> None:
    """Add columns the models have gained since the database was created.

    create_all() only creates whole tables; it will not touch one that
    already exists, so a new column would silently never appear and every
    query naming it would fail.

    This is deliberately the smallest thing that works, not a migration
    framework: it only ever ADDs a nullable column, which SQLite does
    in place without rewriting the table. It cannot drop, rename or retype
    anything, so it cannot lose data. Anything beyond that needs a real
    migration tool and a conversation.
    """
    inspector = inspect(engine)

    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue

        existing = {column["name"] for column in inspector.get_columns(table.name)}

        for column in table.columns:
            if column.name in existing or not column.nullable:
                continue
            column_type = column.type.compile(dialect=engine.dialect)
            with engine.begin() as connection:
                connection.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type}')
                )
