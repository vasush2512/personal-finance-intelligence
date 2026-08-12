"""Tests for the SMS delivery layer.

No test here may make a real network call. What matters is the wiring and the
safety defaults: nothing is sent unless someone deliberately configured it,
missing credentials fail loudly rather than silently doing nothing, and a
provider's refusal surfaces as an error instead of a pretend success.
"""

import pytest

from app.services import sms


def settings(**overrides):
    base = {"provider": "console"}
    base.update(overrides)
    return base


@pytest.fixture
def no_network(monkeypatch):
    """Explode if anything tries to actually reach a provider."""
    def forbidden(*args, **kwargs):
        raise AssertionError("a test tried to make a real HTTP call")

    monkeypatch.setattr(sms, "_post", forbidden)


# --- defaults -------------------------------------------------------------

def test_nothing_is_configured_by_default(monkeypatch, no_network):
    """Sending SMS costs money. It stays off until switched on."""
    monkeypatch.setattr(sms, "sms_settings", lambda: settings())

    assert sms.is_configured() is False
    assert sms.send_code("9876543210", "123456") == "on_screen"


def test_a_configured_provider_reports_as_configured(monkeypatch, no_network):
    monkeypatch.setattr(
        sms, "sms_settings", lambda: settings(provider="fast2sms", fast2sms_api_key="k")
    )

    assert sms.is_configured() is True


def test_an_unknown_provider_is_refused(monkeypatch, no_network):
    monkeypatch.setattr(sms, "sms_settings", lambda: settings(provider="pigeon"))

    with pytest.raises(sms.SmsError) as error:
        sms.send_code("9876543210", "123456")

    assert "pigeon" in str(error.value)


# --- missing credentials --------------------------------------------------

@pytest.mark.parametrize(
    "provider,expected",
    [
        ("twilio", "twilio_account_sid"),
        ("msg91", "msg91_authkey"),
        ("fast2sms", "fast2sms_api_key"),
    ],
)
def test_missing_credentials_say_what_is_missing(
    monkeypatch, no_network, provider, expected
):
    """A half-configured provider must not fail silently at the network."""
    monkeypatch.setattr(sms, "sms_settings", lambda: settings(provider=provider))

    with pytest.raises(sms.SmsError) as error:
        sms.send_code("9876543210", "123456")

    assert expected in str(error.value)


# --- what actually goes out -----------------------------------------------

def test_twilio_is_given_the_number_in_e164(monkeypatch):
    captured = {}

    def fake_post(url, data, headers=None, as_json=False):
        captured.update({"url": url, "data": data, "headers": headers})
        return "{}"

    monkeypatch.setattr(sms, "_post", fake_post)
    monkeypatch.setattr(
        sms,
        "sms_settings",
        lambda: settings(
            provider="twilio",
            twilio_account_sid="AC123",
            twilio_auth_token="secret",
            twilio_from="+15551234567",
        ),
    )

    assert sms.send_code("9876543210", "123456") == "sms"
    assert captured["data"]["To"] == "+919876543210"
    assert "123456" in captured["data"]["Body"]
    assert captured["headers"]["Authorization"].startswith("Basic ")


def test_the_message_warns_against_sharing_the_code():
    """Standard, and the one line that does the most against phone scams."""
    assert "not share" in sms._message("123456").lower()
    assert "123456" in sms._message("123456")


def test_a_provider_refusal_becomes_an_error(monkeypatch):
    monkeypatch.setattr(sms, "_post", lambda *a, **k: '{"return":false,"message":"bad key"}')
    monkeypatch.setattr(
        sms, "sms_settings", lambda: settings(provider="fast2sms", fast2sms_api_key="k")
    )

    with pytest.raises(sms.SmsError):
        sms.send_code("9876543210", "123456")


def test_the_console_provider_does_not_claim_delivery(monkeypatch, no_network):
    monkeypatch.setattr(sms, "sms_settings", lambda: settings(provider="console"))

    assert sms.send_code("9876543210", "123456") == "on_screen"
