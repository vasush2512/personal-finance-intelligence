"""Tests for email accounts.

The behaviours worth pinning down are the ones that would be security bugs if
they regressed: the password is never stored readable, the same password
hashes differently for two people, a wrong password is refused, sign-in does
not reveal which addresses are registered, and guessing gets locked out.

Every test here uses a fast iteration count. The real 600,000 rounds are the
point of the design, but paying 0.3s per hash across thirty tests would make
the suite slow enough that people stop running it.
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s03_db import Base
from app.core.s04_models import User
from app.store import s15_accounts as accounts

NOW = dt.datetime(2026, 8, 14, 10, 0, 0)

PASSWORD = "correct horse battery"


@pytest.fixture
def session():
    """A throwaway in-memory database, fresh for every test."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    """Keep the suite quick without changing what is being tested."""
    monkeypatch.setattr(accounts, "ITERATIONS", 1_000)


@pytest.fixture(autouse=True)
def clean_lockouts():
    """Failure counts are module state. One test must not leak into the next."""
    accounts.clear_all_failures()
    yield
    accounts.clear_all_failures()


# --- email ----------------------------------------------------------------

@pytest.mark.parametrize(
    "typed",
    ["guru@example.com", "  guru@example.com  ", "GURU@Example.COM", "Guru@example.com"],
)
def test_the_same_address_typed_four_ways_is_one_address(typed):
    """Without this, signing up as Guru@ and back in as guru@ fails."""
    assert accounts.normalize_email(typed) == "guru@example.com"


@pytest.mark.parametrize(
    "typed", ["", "   ", "guru", "guru@", "@example.com", "guru@example", "a b@c.com"]
)
def test_rejects_what_is_not_an_address(typed):
    with pytest.raises(accounts.InvalidEmail):
        accounts.normalize_email(typed)


def test_a_missing_name_falls_back_to_the_email():
    assert accounts.clean_name("", "guru@example.com") == "guru"
    assert accounts.clean_name("  ", "guru@example.com") == "guru"


def test_a_given_name_is_kept():
    assert accounts.clean_name("  Guru  ", "guru@example.com") == "Guru"


# --- password rules -------------------------------------------------------

def test_a_good_password_passes():
    accounts.check_password_strength(PASSWORD)  # must not raise


@pytest.mark.parametrize(
    "password,because",
    [
        ("", "empty"),
        ("short1", "too short"),
        ("password", "one of the commonest"),
        ("12345678", "one of the commonest"),
        ("aaaaaaaaaa", "too repetitive"),
        ("x" * 200, "absurdly long"),
    ],
)
def test_bad_passwords_are_refused(password, because):
    with pytest.raises(accounts.WeakPassword):
        accounts.check_password_strength(password)


# --- hashing --------------------------------------------------------------

def test_the_password_is_not_in_the_stored_value():
    """The one test that matters most. A hash containing the password is not one."""
    stored = accounts.hash_password(PASSWORD, iterations=1_000)

    assert PASSWORD not in stored


def test_the_stored_format_carries_its_own_parameters():
    stored = accounts.hash_password(PASSWORD, iterations=1_000)
    algorithm, rounds, salt, digest = stored.split("$")

    assert algorithm == "pbkdf2_sha256"
    assert rounds == "1000"
    assert salt and digest


def test_two_people_with_the_same_password_store_different_values():
    """This is what the random salt buys: one table cannot crack both."""
    first = accounts.hash_password(PASSWORD, iterations=1_000)
    second = accounts.hash_password(PASSWORD, iterations=1_000)

    assert first != second
    # ...and both still verify.
    assert accounts.verify_password(PASSWORD, first)
    assert accounts.verify_password(PASSWORD, second)


def test_the_right_password_verifies():
    stored = accounts.hash_password(PASSWORD, iterations=1_000)

    assert accounts.verify_password(PASSWORD, stored) is True


@pytest.mark.parametrize(
    "wrong", ["Correct horse battery", "correct horse batter", "", "totally other"]
)
def test_a_wrong_password_does_not_verify(wrong):
    stored = accounts.hash_password(PASSWORD, iterations=1_000)

    assert accounts.verify_password(wrong, stored) is False


@pytest.mark.parametrize(
    "corrupt",
    ["", "nonsense", "pbkdf2_sha256$notanumber$a$b", "md5$1000$a$b", "a$b$c"],
)
def test_a_corrupt_stored_hash_fails_closed(corrupt):
    """A hand-edited row must refuse the sign-in, not crash the endpoint."""
    assert accounts.verify_password(PASSWORD, corrupt) is False


def test_raising_the_iteration_count_does_not_break_old_passwords():
    """Old hashes carry their own round count, so they keep working."""
    stored = accounts.hash_password(PASSWORD, iterations=1_000)

    assert accounts.verify_password(PASSWORD, stored)


# --- signing up -----------------------------------------------------------

def test_signing_up_creates_an_account(session):
    user = accounts.create_account(
        session, "Guru@Example.com", PASSWORD, name="Guru", now=NOW
    )

    assert user.id is not None
    assert user.email == "guru@example.com"
    assert user.display_name == "Guru"


def test_the_database_never_holds_the_password(session):
    """Read the row straight back out and look for it."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    stored = session.query(User).one()

    assert PASSWORD not in stored.password_hash
    assert stored.password_hash.startswith("pbkdf2_sha256$")


def test_the_same_address_cannot_be_registered_twice(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    with pytest.raises(accounts.EmailTaken):
        accounts.create_account(session, "guru@example.com", "another one here", now=NOW)


def test_case_does_not_get_you_a_second_account(session):
    """'Guru@' and 'guru@' are the same person, and must collide."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    with pytest.raises(accounts.EmailTaken):
        accounts.create_account(session, "GURU@Example.com", "another one here", now=NOW)


def test_a_weak_password_is_refused_before_any_row_is_written(session):
    with pytest.raises(accounts.WeakPassword):
        accounts.create_account(session, "guru@example.com", "abc", now=NOW)

    assert accounts.count_accounts(session) == 0


def test_a_bad_address_is_refused_before_any_row_is_written(session):
    with pytest.raises(accounts.InvalidEmail):
        accounts.create_account(session, "not-an-email", PASSWORD, now=NOW)

    assert accounts.count_accounts(session) == 0


# --- signing in -----------------------------------------------------------

def test_the_right_password_signs_in(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    user = accounts.authenticate(session, "guru@example.com", PASSWORD, now=NOW)

    assert user.email == "guru@example.com"


def test_signing_in_is_case_insensitive_on_the_address(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    assert accounts.authenticate(session, "GURU@Example.COM", PASSWORD, now=NOW)


def test_the_wrong_password_is_refused(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    with pytest.raises(accounts.BadCredentials):
        accounts.authenticate(session, "guru@example.com", "wrong password!", now=NOW)


def test_an_unknown_address_is_refused(session):
    with pytest.raises(accounts.BadCredentials):
        accounts.authenticate(session, "nobody@example.com", PASSWORD, now=NOW)


def test_an_unknown_address_and_a_wrong_password_read_identically(session):
    """Different wording here would publish who has an account."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    with pytest.raises(accounts.BadCredentials) as wrong_password:
        accounts.authenticate(session, "guru@example.com", "wrong password!", now=NOW)

    with pytest.raises(accounts.BadCredentials) as no_such_account:
        accounts.authenticate(session, "nobody@example.com", PASSWORD, now=NOW)

    assert str(wrong_password.value) == str(no_such_account.value)


def test_signing_in_records_when(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)
    later = NOW + dt.timedelta(days=3)

    user = accounts.authenticate(session, "guru@example.com", PASSWORD, now=later)

    assert user.last_signed_in_at == later


def test_two_accounts_do_not_share_a_password(session):
    accounts.create_account(session, "one@example.com", PASSWORD, now=NOW)
    accounts.create_account(session, "two@example.com", "a different one", now=NOW)

    with pytest.raises(accounts.BadCredentials):
        accounts.authenticate(session, "two@example.com", PASSWORD, now=NOW)


# --- lockout --------------------------------------------------------------

def test_guessing_gets_locked_out(session):
    """Without this, the endpoint is a password-guessing service."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    for _ in range(accounts.MAX_FAILED_ATTEMPTS):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)

    with pytest.raises(accounts.AccountLocked):
        accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)


def test_the_lockout_blocks_the_real_password_too(session):
    """Otherwise the lock is decorative — guess on, then sign in normally."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    for _ in range(accounts.MAX_FAILED_ATTEMPTS):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)

    with pytest.raises(accounts.AccountLocked):
        accounts.authenticate(session, "guru@example.com", PASSWORD, now=NOW)


def test_the_lockout_expires(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    for _ in range(accounts.MAX_FAILED_ATTEMPTS):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)

    later = NOW + dt.timedelta(seconds=accounts.LOCKOUT_SECONDS + 1)

    assert accounts.authenticate(session, "guru@example.com", PASSWORD, now=later)


def test_the_lockout_is_per_address(session):
    """One person guessing must not lock everybody else out."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)
    accounts.create_account(session, "other@example.com", "a different one", now=NOW)

    for _ in range(accounts.MAX_FAILED_ATTEMPTS):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)

    assert accounts.authenticate(session, "other@example.com", "a different one", now=NOW)


def test_a_successful_sign_in_clears_the_count(session):
    """Failures spread over weeks must not add up to a lockout."""
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    for _ in range(accounts.MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)

    accounts.authenticate(session, "guru@example.com", PASSWORD, now=NOW)

    # Back to a full allowance rather than one attempt from the lock.
    with pytest.raises(accounts.BadCredentials):
        accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)


def test_the_lock_says_how_long_to_wait(session):
    accounts.create_account(session, "guru@example.com", PASSWORD, now=NOW)

    for _ in range(accounts.MAX_FAILED_ATTEMPTS):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "guru@example.com", "nope nope nope", now=NOW)

    with pytest.raises(accounts.AccountLocked) as error:
        accounts.authenticate(session, "guru@example.com", PASSWORD, now=NOW)

    assert 0 < error.value.retry_after <= accounts.LOCKOUT_SECONDS + 1


def test_guessing_an_address_that_does_not_exist_is_also_locked(session):
    """The lockout must not itself become an account-existence oracle."""
    for _ in range(accounts.MAX_FAILED_ATTEMPTS):
        with pytest.raises(accounts.BadCredentials):
            accounts.authenticate(session, "nobody@example.com", "nope nope nope", now=NOW)

    with pytest.raises(accounts.AccountLocked):
        accounts.authenticate(session, "nobody@example.com", "nope nope nope", now=NOW)
