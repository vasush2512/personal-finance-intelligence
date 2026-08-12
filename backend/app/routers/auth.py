"""Phone sign-in for the lock screen.

Demonstration only — see services/otp.py for exactly what this is not.
Nothing here creates a session, and no other endpoint asks whether you
passed it.
"""

from fastapi import APIRouter, HTTPException

from app.schemas import OtpChallenge, OtpRequest, OtpVerification, OtpVerify
from app.services import otp

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpChallenge)
def request_otp(body: OtpRequest):
    """Issue a code for a phone number.

    The response carries the code, because there is no SMS provider to
    deliver it with. A real implementation returns nothing of the sort.
    """
    try:
        return otp.request_code(body.phone)
    except otp.TooSoon as error:
        # 429 with Retry-After is the honest answer to "too fast", and it
        # lets the UI count down instead of guessing.
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after)},
        )
    except otp.DailyLimitReached as error:
        raise HTTPException(status_code=429, detail=str(error))
    except otp.DeliveryFailed as error:
        # 502: the request was fine, the provider was not. Saying so is what
        # lets someone tell a bad API key from a wrong phone number.
        raise HTTPException(status_code=502, detail=str(error))
    except otp.InvalidPhone as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/otp/verify", response_model=OtpVerification)
def verify_otp(body: OtpVerify):
    """Check a code. Correct codes are consumed; wrong ones are counted."""
    try:
        return otp.verify_code(body.phone, body.code)
    except otp.WrongCode as error:
        raise HTTPException(
            status_code=401,
            detail={"message": str(error), "attempts_left": error.attempts_left},
        )
    except (otp.CodeExpired, otp.TooManyAttempts, otp.NoChallenge) as error:
        raise HTTPException(status_code=410, detail=str(error))
    except otp.InvalidPhone as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/sign-out", status_code=204)
def sign_out(body: OtpRequest):
    """Forget any outstanding challenge for this number.

    There is no session to end. This only clears the pending code, so a
    half-finished sign-in cannot be resumed after signing out.
    """
    otp.forget(body.phone)
