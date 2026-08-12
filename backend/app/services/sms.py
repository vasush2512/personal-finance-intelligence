"""Sending a one-time code to an actual phone.

Providers are pluggable and chosen by configuration. Nothing here has a
default account or a built-in key: sending SMS costs money and can be abused,
so it stays off until someone deliberately turns it on with their own
credentials.

  console   no SMS. The code is logged and returned to the browser. This is
            the default, and the only mode where the API hands back the code.
  twilio    global, needs an Indian sender registration for Indian numbers
  msg91     India-first, OTP route
  fast2sms  India-only, simple key

Adding a provider means writing one function and adding one line to
PROVIDERS. Everything else — expiry, attempt caps, cooldown — is already in
otp.py and does not change.

Uses urllib from the standard library rather than requests or httpx, because
neither is in the project's dependencies and one HTTP POST does not justify
adding one.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from app.config import sms_settings

log = logging.getLogger("app.sms")

TIMEOUT_SECONDS = 12


class SmsError(Exception):
    """Delivery failed. The message is safe to show the user."""


def _post(url, data, headers=None, as_json=False):
    """One HTTP POST, with the provider's error text preserved on failure."""
    body = json.dumps(data).encode() if as_json else urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers or {})
    if as_json:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise SmsError(f"SMS provider rejected the request ({error.code}): {detail}")
    except urllib.error.URLError as error:
        raise SmsError(f"Could not reach the SMS provider: {error.reason}")
    except TimeoutError:
        raise SmsError("The SMS provider timed out.")


def _message(code: str) -> str:
    return (
        f"{code} is your Expense Tracker verification code. "
        "It expires in 5 minutes. Do not share it with anyone."
    )


# --- providers ------------------------------------------------------------

def send_via_console(phone: str, code: str, settings) -> str:
    """No provider configured. Log it and let the browser show it."""
    log.warning("SMS not configured — code for +91%s is %s", phone, code)
    return "on_screen"


def send_via_twilio(phone: str, code: str, settings) -> str:
    account = settings.get("twilio_account_sid")
    token = settings.get("twilio_auth_token")
    sender = settings.get("twilio_from")

    if not (account and token and sender):
        raise SmsError(
            "Twilio needs twilio_account_sid, twilio_auth_token and twilio_from."
        )

    import base64

    credentials = base64.b64encode(f"{account}:{token}".encode()).decode()
    _post(
        f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json",
        {"To": f"+91{phone}", "From": sender, "Body": _message(code)},
        headers={"Authorization": f"Basic {credentials}"},
    )
    return "sms"


def send_via_msg91(phone: str, code: str, settings) -> str:
    key = settings.get("msg91_authkey")
    template = settings.get("msg91_template_id")

    if not (key and template):
        raise SmsError("MSG91 needs msg91_authkey and msg91_template_id.")

    # MSG91's OTP route takes the code as a template variable; the message
    # body itself lives in the DLT-approved template on their side.
    response = _post(
        "https://control.msg91.com/api/v5/otp"
        f"?template_id={urllib.parse.quote(template)}"
        f"&mobile=91{phone}&otp={urllib.parse.quote(code)}",
        {},
        headers={"authkey": key, "accept": "application/json"},
        as_json=True,
    )
    if '"type":"error"' in response.replace(" ", ""):
        raise SmsError(f"MSG91 refused the message: {response[:200]}")
    return "sms"


def send_via_fast2sms(phone: str, code: str, settings) -> str:
    key = settings.get("fast2sms_api_key")
    if not key:
        raise SmsError("Fast2SMS needs fast2sms_api_key.")

    response = _post(
        "https://www.fast2sms.com/dev/bulkV2",
        {"variables_values": code, "route": "otp", "numbers": phone},
        headers={"authorization": key},
    )
    if '"return":false' in response.replace(" ", ""):
        raise SmsError(f"Fast2SMS refused the message: {response[:200]}")
    return "sms"


PROVIDERS = {
    "console": send_via_console,
    "twilio": send_via_twilio,
    "msg91": send_via_msg91,
    "fast2sms": send_via_fast2sms,
}


# --- entry point ----------------------------------------------------------

def is_configured() -> bool:
    """True when a real provider is selected."""
    return sms_settings().get("provider", "console") != "console"


def send_code(phone: str, code: str) -> str:
    """Deliver a code. Returns 'sms' or 'on_screen'.

    The code is never logged when a provider is configured — a one-time code
    sitting in a log file is a one-time code that is no longer one-time.
    """
    settings = sms_settings()
    provider = settings.get("provider", "console").lower()

    sender = PROVIDERS.get(provider)
    if sender is None:
        raise SmsError(
            f"Unknown SMS provider {provider!r}. "
            f"Choose one of: {', '.join(sorted(PROVIDERS))}."
        )

    delivery = sender(phone, code, settings)
    if delivery == "sms":
        log.info("Sent a code to +91%s via %s", phone, provider)
    return delivery
