"""The paths the whole app hangs off.

These exist because of a real failure: when config.py moved from app/ into
app/core/ during the module reorganisation, BASE_DIR was computed by walking up
a fixed two directories. The extra level meant it landed on backend/app/ rather
than backend/, so the application created and used an empty
backend/app/data/expenses.db while the real database sat untouched beside it.

Nothing raised. The API answered normally, with zero rows. That is the worst
shape a bug can take, and a test that pins the resolved path is the cheapest
possible guard against it happening again.
"""

from app.core import s02_config as config


def test_base_dir_is_the_backend_directory():
    """Not backend/app, and not the repository root."""
    assert config.BASE_DIR.name == "backend"


def test_data_dir_sits_directly_under_backend():
    assert config.DATA_DIR == config.BASE_DIR / "data"
    assert config.DATA_DIR.parent.name == "backend"


def test_the_real_database_is_the_one_that_gets_used():
    """The file the app opens must be the one holding the sample statement."""
    assert config.DATABASE_PATH == config.BASE_DIR / "data" / "expenses.db"
    assert config.DATABASE_URL.endswith("backend/data/expenses.db") or \
        config.DATABASE_URL.replace("\\", "/").endswith("backend/data/expenses.db")


def test_model_and_sample_live_beside_the_database():
    assert config.MODEL_PATH.parent == config.DATA_DIR
    assert config.SAMPLE_STATEMENT_PATH.parent == config.DATA_DIR


def test_the_sample_statement_is_actually_there():
    """A path that points nowhere is the same bug in a different disguise."""
    assert config.SAMPLE_STATEMENT_PATH.is_file()
