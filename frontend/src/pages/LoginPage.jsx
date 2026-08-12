import { useEffect, useMemo, useRef, useState } from "react";

import * as api from "../api.js";
import OtpInput from "../components/OtpInput.jsx";
import "../login.css";

/**
 * Phone sign-in, in two steps: number, then the code sent to it.
 *
 * Read this before judging it: it is a demonstration of an OTP flow, not
 * security. There is no SMS provider, so the code comes back in the response
 * and is shown on screen. Verifying creates no session — the API answers
 * every request whether you signed in or not, and the database is
 * unencrypted on disk.
 *
 * The screen says all of that on itself. A sign-in that looks like a lock but
 * is not one teaches the person using it the wrong thing about their data.
 *
 * What is modelled honestly, because these are the parts worth knowing:
 * expiry, a cap on wrong guesses, a resend cooldown, and single use.
 */

const STORAGE_KEY = "expense-tracker-session";

const CHIPS = [
  { label: "Swiggy", amount: "₹409", color: "#2a78d6" },
  { label: "Blinkit", amount: "₹1,051", color: "#1baf7a" },
  { label: "House rent", amount: "₹11,722", color: "#eda100" },
  { label: "Uber", amount: "₹180", color: "#e87ba4" },
  { label: "Salary", amount: "₹82,000", color: "#1baf7a" },
  { label: "Netflix", amount: "₹649", color: "#e34948" },
  { label: "Apollo", amount: "₹1,330", color: "#4a3aa7" },
  { label: "IRCTC", amount: "₹2,078", color: "#2a78d6" },
  { label: "DMart", amount: "₹3,471", color: "#eda100" },
  { label: "Udemy", amount: "₹2,611", color: "#3987e5" },
];

/** The signed-in phone, or null. */
export function currentSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // Private browsing can make sessionStorage throw. Failing open is right:
    // this gate protects nothing, so it must never lock anybody out.
    return { phone: "", display_phone: "guest", degraded: true };
  }
}

function rememberSession(session) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* the screen simply reappears next time */
  }
}

export function clearSession() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to clean up */
  }
}

export default function LoginPage({ onSignedIn }) {
  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shaking, setShaking] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const [expiresIn, setExpiresIn] = useState(0);
  const [resendIn, setResendIn] = useState(0);

  const phoneRef = useRef(null);

  useEffect(() => {
    if (step === "phone") phoneRef.current?.focus();
  }, [step]);

  /** One ticker drives both countdowns. */
  useEffect(() => {
    if (step !== "code") return undefined;
    const timer = setInterval(() => {
      setExpiresIn((seconds) => Math.max(0, seconds - 1));
      setResendIn((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [step]);

  const chips = useMemo(
    () =>
      CHIPS.map((chip, index) => {
        // Two bands down the sides, leaving the middle clear for the card.
        const onLeft = index % 2 === 0;
        const offset = ((index * 7) % 18) - 9;
        return {
          ...chip,
          left: `${(onLeft ? 16 : 84) + offset}%`,
          duration: `${17 + ((index * 3.1) % 11)}s`,
          // Negative delays start each chip partway through its loop, so the
          // screen is already populated on the first frame.
          delay: `${-(index * 2.3).toFixed(1)}s`,
        };
      }),
    []
  );

  function fail(message) {
    setError(message);
    setShaking(true);
    setTimeout(() => setShaking(false), 400);
  }

  async function sendCode(event) {
    event?.preventDefault();
    if (busy) return;

    setBusy(true);
    setError("");
    try {
      const issued = await api.requestOtp(phone);
      setChallenge(issued);
      setExpiresIn(issued.expires_in);
      setResendIn(issued.resend_in);
      setCode("");
      setStep("code");
    } catch (requestError) {
      fail(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(submitted) {
    const entered = (submitted ?? code).replace(/\D/g, "");
    if (busy || entered.length < 6) return;

    setBusy(true);
    setError("");
    try {
      const result = await api.verifyOtp(challenge.phone, entered);
      rememberSession(result);
      setLeaving(true);
      // Let the screen finish lifting away before the dashboard mounts.
      setTimeout(() => onSignedIn(result), 620);
    } catch (verifyError) {
      setBusy(false);
      setCode("");
      fail(verifyError.message);
    }
  }

  function changeNumber() {
    setStep("phone");
    setCode("");
    setError("");
    setChallenge(null);
  }

  const minutes = Math.floor(expiresIn / 60);
  const seconds = String(expiresIn % 60).padStart(2, "0");

  return (
    <div className={`lock ${leaving ? "unlocking" : ""}`}>
      <div className="lock-aurora" aria-hidden="true">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
      </div>

      <div className="lock-grid" aria-hidden="true" />

      <div className="lock-ticker" aria-hidden="true">
        {chips.map((chip) => (
          <span
            key={chip.label}
            className="ticker-chip"
            style={{
              left: chip.left,
              bottom: 0,
              animationDuration: chip.duration,
              animationDelay: chip.delay,
            }}
          >
            <span className="dot" style={{ background: chip.color }} />
            {chip.label}
            <span className="amount">{chip.amount}</span>
          </span>
        ))}
      </div>

      <form
        className={`lock-card ${shaking ? "shake" : ""}`}
        onSubmit={step === "phone" ? sendCode : (event) => {
          event.preventDefault();
          submitCode();
        }}
        aria-labelledby="lock-title"
      >
        <div className="lock-mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>

        <h1 className="lock-title" id="lock-title">
          Expense Tracker
        </h1>

        {step === "phone" ? (
          <div className="step stagger" key="phone">
            <p className="lock-subtitle">
              Sign in with your mobile number. We will send a six-digit code.
            </p>

            <div className="lock-field phone-field">
              <span className="country" aria-hidden="true">
                +91
              </span>
              <input
                ref={phoneRef}
                id="phone"
                type="tel"
                inputMode="numeric"
                autoComplete="tel"
                value={phone}
                placeholder=" "
                maxLength={14}
                onChange={(event) => setPhone(event.target.value)}
                aria-invalid={Boolean(error)}
              />
              <label htmlFor="phone">Mobile number</label>
            </div>

            <button className="lock-button" type="submit" disabled={busy}>
              {busy ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Sending…
                </>
              ) : (
                "Send code"
              )}
            </button>

            <p className="lock-error" role="alert">
              {error}
            </p>
          </div>
        ) : (
          <div className="step stagger" key="code">
            <p className="lock-subtitle">
              {challenge.delivery === "sms"
                ? "We sent a six-digit code to "
                : "Code generated for "}
              <strong>{challenge.display_phone}</strong>.{" "}
              <button type="button" className="link" onClick={changeNumber}>
                Change
              </button>
            </p>

            {/* Only when nothing could carry the code. Once a provider is
                configured the API stops returning it, and this disappears. */}
            {challenge.delivery === "on_screen" && challenge.demo_code && (
              <div className="demo-code" role="status">
                <span>No SMS provider configured — your code is</span>
                <strong>{challenge.demo_code}</strong>
              </div>
            )}

            <OtpInput
              value={code}
              onChange={setCode}
              onComplete={submitCode}
              disabled={busy || expiresIn === 0}
            />

            <button
              className="lock-button"
              type="submit"
              disabled={busy || code.replace(/\D/g, "").length < 6}
            >
              {busy ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Verifying…
                </>
              ) : (
                "Verify and open"
              )}
            </button>

            <div className="code-meta">
              {expiresIn > 0 ? (
                <span>
                  Expires in {minutes}:{seconds}
                </span>
              ) : (
                <span className="expired">Code expired</span>
              )}

              <button
                type="button"
                className="link"
                onClick={sendCode}
                disabled={busy || resendIn > 0}
              >
                {resendIn > 0 ? `Resend in ${resendIn}s` : "Resend code"}
              </button>
            </div>

            <p className="lock-error" role="alert">
              {error}
            </p>
          </div>
        )}

        <p className="lock-disclosure">
          {challenge?.delivery === "sms" ? (
            <>
              The code was sent by SMS and is not shown here. Signing in still
              creates no session on the server — the API answers whether you
              sign in or not, and your transactions sit unencrypted in{" "}
              <span className="lock-hint">backend/data/expenses.db</span>.
            </>
          ) : (
            <>
              No SMS provider is configured, so the code is shown above instead
              of sent. Copy{" "}
              <span className="lock-hint">backend/sms.ini.example</span> to{" "}
              <span className="lock-hint">backend/sms.ini</span> and add your
              provider key to send it for real. Signing in creates no session
              either way.
            </>
          )}
        </p>
      </form>
    </div>
  );
}
