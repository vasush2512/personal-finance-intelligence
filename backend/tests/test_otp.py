"""Tests for the one-time code flow.

The behaviours worth testing are the ones that would be security properties
if this were real: codes expire, guesses are capped, a used code is dead, and
resending is rate limited. Those hold here even though nothing is protected.
"""

import datetime as dt

import pytest

from app.services import otp

NOW = dt.datetime(2026, 8, 13, 10, 0, 0)


@pytest.fixture(autouse=True)
def clean_store():
    """Challenges are module state. One test must not leak into the next."""
    otp.clear_all()
    yield
    otp.clear_all()


# --- phone numbers --------------------------------------------------------

@pytest.mark.parametrize(
    "typed",
    ["9876543210", "+91 98765 43210", "+919876543210", "098765 43210", "98765-43210"],
)
def test_the_same_number_typed_five_ways_is_one_number(typed):
    assert otp.normalize_phone(typed) == "9876543210"


@pytest.mark.parametrize(
    "typed", ["12345", "5876543210", "98765432101", "", "not a phone"]
)
def test_rejects_what_is_not_an_indian_mobile(typed):
    with pytest.raises(otp.InvalidPhone):
        otp.normalize_phone(typed)


def test_display_format():
    assert otp.format_phone("9876543210") == "+91 98765 43210"


# --- issuing --------------------------------------------------------------

def test_issues_a_six_digit_code():
    challenge = otp.request_code("9876543210", now=NOW)

    assert len(challenge["demo_code"]) == 6
    assert challenge["demo_code"].isdigit()
    assert challenge["display_phone"] == "+91 98765 43210"


def test_resending_too_soon_is_refused():
    otp.request_code("9876543210", now=NOW)

    with pytest.raises(otp.TooSoon) as error:
        otp.request_code("9876543210", now=NOW + dt.timedelta(seconds=5))

    assert 0 < error.value.retry_after <= otp.RESEND_COOLDOWN_SECONDS


def test_resending_after_the_cooldown_issues_a_new_code():
    first = otp.request_code("9876543210", now=NOW)
    later = NOW + dt.timedelta(seconds=otp.RESEND_COOLDOWN_SECONDS + 1)

    second = otp.request_code("9876543210", now=later)

    # The old code must stop working, or a resend doubles the guessable set.
    with pytest.raises(otp.WrongCode):
        otp.verify_code("9876543210", first["demo_code"], now=later)
    assert otp.verify_code("9876543210", second["demo_code"], now=later)["verified"]


def test_two_numbers_have_their_own_codes():
    a = otp.request_code("9876543210", now=NOW)
    b = otp.request_code("9000000001", now=NOW)

    with pytest.raises(otp.WrongCode):
        otp.verify_code("9000000001", a["demo_code"], now=NOW)
    assert otp.verify_code("9000000001", b["demo_code"], now=NOW)["verified"]


# --- verifying ------------------------------------------------------------

def test_the_right_code_verifies():
    challenge = otp.request_code("9876543210", now=NOW)

    result = otp.verify_code("9876543210", challenge["demo_code"], now=NOW)

    assert result["verified"] is True
    assert result["phone"] == "9876543210"


def test_spaces_in_the_typed_code_are_ignored():
    challenge = otp.request_code("9876543210", now=NOW)
    spaced = " ".join(challenge["demo_code"])

    assert otp.verify_code("9876543210", spaced, now=NOW)["verified"]


def test_a_code_works_only_once():
    challenge = otp.request_code("9876543210", now=NOW)
    otp.verify_code("9876543210", challenge["demo_code"], now=NOW)

    with pytest.raises(otp.NoChallenge):
        otp.verify_code("9876543210", challenge["demo_code"], now=NOW)


def test_a_code_expires():
    challenge = otp.request_code("9876543210", now=NOW)
    too_late = NOW + dt.timedelta(seconds=otp.CODE_TTL_SECONDS + 1)

    with pytest.raises(otp.CodeExpired):
        otp.verify_code("9876543210", challenge["demo_code"], now=too_late)


def test_a_code_still_works_just_before_it_expires():
    challenge = otp.request_code("9876543210", now=NOW)
    just_in_time = NOW + dt.timedelta(seconds=otp.CODE_TTL_SECONDS - 1)

    assert otp.verify_code("9876543210", challenge["demo_code"], now=just_in_time)


def test_guesses_are_counted_down():
    otp.request_code("9876543210", now=NOW)

    with pytest.raises(otp.WrongCode) as error:
        otp.verify_code("9876543210", "000000", now=NOW)

    assert error.value.attempts_left == otp.MAX_ATTEMPTS - 1


def test_guessing_is_capped():
    challenge = otp.request_code("9876543210", now=NOW)
    wrong = "000000" if challenge["demo_code"] != "000000" else "111111"

    for _ in range(otp.MAX_ATTEMPTS - 1):
        with pytest.raises(otp.WrongCode):
            otp.verify_code("9876543210", wrong, now=NOW)

    with pytest.raises(otp.TooManyAttempts):
        otp.verify_code("9876543210", wrong, now=NOW)


def test_the_real_code_stops_working_once_guessing_is_capped():
    """Otherwise the cap is decorative — you could exhaust it and continue."""
    challenge = otp.request_code("9876543210", now=NOW)
    wrong = "000000" if challenge["demo_code"] != "000000" else "111111"

    for _ in range(otp.MAX_ATTEMPTS):
        with pytest.raises(otp.OtpError):
            otp.verify_code("9876543210", wrong, now=NOW)

    with pytest.raises(otp.NoChallenge):
        otp.verify_code("9876543210", challenge["demo_code"], now=NOW)


def test_verifying_without_asking_first():
    with pytest.raises(otp.NoChallenge):
        otp.verify_code("9876543210", "123456", now=NOW)


# --- sign out -------------------------------------------------------------

def test_signing_out_drops_a_pending_code():
    challenge = otp.request_code("9876543210", now=NOW)

    otp.forget("9876543210")

    with pytest.raises(otp.NoChallenge):
        otp.verify_code("9876543210", challenge["demo_code"], now=NOW)


def test_signing_out_with_a_nonsense_number_is_harmless():
    otp.forget("not a phone")  # must not raise
