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


@pytest.fixture
def sent(monkeypatch):
    """Pretend a provider is configured, and record what it was handed.

    No test may make a real HTTP call to an SMS provider: that would cost
    money, need credentials, and text a stranger.
    """
    messages = []

    def fake_send(phone, code):
        messages.append({"phone": phone, "code": code})
        return "sms"

    monkeypatch.setattr(otp.sms, "send_code", fake_send)
    return messages


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


# --- delivery -------------------------------------------------------------

def test_the_code_goes_to_the_provider(sent):
    otp.request_code("+91 98765 43210", now=NOW)

    assert len(sent) == 1
    assert sent[0]["phone"] == "9876543210"
    assert len(sent[0]["code"]) == 6


def test_the_api_stops_returning_the_code_once_it_can_be_sent(sent):
    """The single most important line in this file.

    A one-time code the API hands back is not a one-time code.
    """
    challenge = otp.request_code("9876543210", now=NOW)

    assert challenge["delivery"] == "sms"
    assert challenge["demo_code"] is None


def test_the_code_is_returned_only_when_nothing_can_carry_it():
    challenge = otp.request_code("9876543210", now=NOW)

    assert challenge["delivery"] == "on_screen"
    assert challenge["demo_code"] is not None


def test_the_sent_code_is_the_one_that_verifies(sent):
    otp.request_code("9876543210", now=NOW)

    result = otp.verify_code("9876543210", sent[0]["code"], now=NOW)

    assert result["verified"] is True


def test_a_refused_message_leaves_the_old_code_working(monkeypatch):
    """A provider outage must not invalidate a code already in someone's hand."""
    first = otp.request_code("9876543210", now=NOW)

    def refuse(phone, code):
        raise otp.sms.SmsError("provider is down")

    monkeypatch.setattr(otp.sms, "send_code", refuse)
    later = NOW + dt.timedelta(seconds=otp.RESEND_COOLDOWN_SECONDS + 1)

    with pytest.raises(otp.DeliveryFailed):
        otp.request_code("9876543210", now=later)

    assert otp.verify_code("9876543210", first["demo_code"], now=later)["verified"]


# --- daily cap ------------------------------------------------------------

def test_a_number_cannot_be_texted_all_day(sent):
    """Without this, an open endpoint is an SMS bomber billed to the owner."""
    when = NOW
    for _ in range(otp.MAX_SENDS_PER_PHONE_PER_DAY):
        otp.request_code("9876543210", now=when)
        when += dt.timedelta(seconds=otp.RESEND_COOLDOWN_SECONDS + 1)

    with pytest.raises(otp.DailyLimitReached):
        otp.request_code("9876543210", now=when)


def test_the_cap_resets_the_next_day(sent):
    when = NOW
    for _ in range(otp.MAX_SENDS_PER_PHONE_PER_DAY):
        otp.request_code("9876543210", now=when)
        when += dt.timedelta(seconds=otp.RESEND_COOLDOWN_SECONDS + 1)

    tomorrow = NOW + dt.timedelta(days=1)
    assert otp.request_code("9876543210", now=tomorrow)["delivery"] == "sms"


def test_the_cap_is_per_number(sent):
    when = NOW
    for _ in range(otp.MAX_SENDS_PER_PHONE_PER_DAY):
        otp.request_code("9876543210", now=when)
        when += dt.timedelta(seconds=otp.RESEND_COOLDOWN_SECONDS + 1)

    # A different number is unaffected by the first one's exhaustion.
    assert otp.request_code("9000000001", now=when)["delivery"] == "sms"


def test_a_refused_message_still_counts_against_the_cap(monkeypatch):
    """Otherwise a failing provider becomes an unlimited retry loop."""
    def refuse(phone, code):
        raise otp.sms.SmsError("nope")

    monkeypatch.setattr(otp.sms, "send_code", refuse)

    when = NOW
    for _ in range(otp.MAX_SENDS_PER_PHONE_PER_DAY):
        with pytest.raises(otp.DeliveryFailed):
            otp.request_code("9876543210", now=when)
        when += dt.timedelta(seconds=otp.RESEND_COOLDOWN_SECONDS + 1)

    with pytest.raises(otp.DailyLimitReached):
        otp.request_code("9876543210", now=when)


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
