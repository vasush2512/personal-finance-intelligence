"""Which DATABASE_URL values the app can actually open a connection with.

The failure this guards against is not subtle at runtime — the process dies on
startup — but it is very hard to read. Handed the `postgresql://` URL a host
prints in its dashboard, SQLAlchemy looks for psycopg 2, which this project
does not install, and raises ModuleNotFoundError. The obvious reading is "a
dependency is missing from requirements.txt", and the obvious fix is to add
the wrong package.
"""

from app.core.s02_config import DATABASE_PATH, DATABASE_URL, normalize_database_url


def test_the_scheme_a_host_hands_out_is_rewritten():
    """`postgresql://` resolves to psycopg 2 unless it is rewritten."""
    assert normalize_database_url("postgresql://user:pw@host:5432/db") == (
        "postgresql+psycopg://user:pw@host:5432/db"
    )


def test_the_legacy_heroku_style_scheme_is_rewritten_too():
    """SQLAlchemy 2.x dropped `postgres://` entirely; several hosts still emit it."""
    assert normalize_database_url("postgres://user:pw@host:5432/db") == (
        "postgresql+psycopg://user:pw@host:5432/db"
    )


def test_an_explicit_driver_is_left_alone():
    """Already correct, and rewriting it would double the prefix."""
    url = "postgresql+psycopg://user:pw@host:5432/db"
    assert normalize_database_url(url) == url


def test_a_url_naming_some_other_driver_is_not_hijacked():
    """If someone deliberately installs psycopg 2, respect the choice."""
    url = "postgresql+psycopg2://user:pw@host:5432/db"
    assert normalize_database_url(url) == url


def test_sqlite_is_untouched():
    assert normalize_database_url("sqlite:///data/expenses.db") == (
        "sqlite:///data/expenses.db"
    )


def test_query_parameters_survive_the_rewrite():
    """Managed databases routinely require sslmode, and losing it fails the connect."""
    assert normalize_database_url("postgresql://u:pw@host/db?sslmode=require") == (
        "postgresql+psycopg://u:pw@host/db?sslmode=require"
    )


def test_a_password_containing_the_scheme_text_is_not_corrupted():
    """Only the leading prefix is replaced, not every occurrence."""
    url = "postgresql://user:postgresql://@host/db"
    assert normalize_database_url(url) == "postgresql+psycopg://user:postgresql://@host/db"


def test_the_default_is_still_the_local_sqlite_file():
    """With DATABASE_URL unset, nothing about local development changes."""
    assert DATABASE_URL == f"sqlite:///{DATABASE_PATH}"
