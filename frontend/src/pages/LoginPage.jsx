import { useEffect, useMemo, useRef, useState } from "react";

import * as api from "../api.js";
import "../login.css";

/**
 * Sign in or create an account, on one screen with two tabs.
 *
 * Read this before judging it: the accounts are real — a row in the database
 * with a properly salted, slow-hashed password, and the password itself is
 * never stored or returned. What signing in does NOT do is protect anything.
 * No other endpoint asks who is calling, so this unlocks the interface and
 * nothing behind it, and the database sits unencrypted on disk.
 *
 * The screen says that on itself. A sign-in that looks like a lock but is not
 * one teaches the person using it the wrong thing about their own data.
 */

const STORAGE_KEY = "expense-tracker-session";

/**
 * Decoration for the sign-in background.
 *
 * Category names only — deliberately no amounts. Earlier these carried rupee
 * figures ("Swiggy ₹409"), which were invented: no statement had been uploaded
 * and nobody was signed in, so there was no data they could have come from.
 * A financial figure on screen has to be a real one or not be there at all,
 * and a decorative one is the easiest kind to mistake for real.
 */
const CHIPS = [
  { label: "Food", color: "#2a78d6" },
  { label: "Groceries", color: "#1baf7a" },
  { label: "Rent", color: "#eda100" },
  { label: "Transport", color: "#e87ba4" },
  { label: "Income", color: "#1baf7a" },
  { label: "Entertainment", color: "#e34948" },
  { label: "Health", color: "#4a3aa7" },
  { label: "Shopping", color: "#2a78d6" },
  { label: "Bills", color: "#eda100" },
  { label: "Education", color: "#3987e5" },
];

/** Must match MIN_PASSWORD_LENGTH in backend/app/services/accounts.py. */
const MIN_PASSWORD_LENGTH = 8;

/** The signed-in account, or null. */
export function currentSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // Fails closed now. This used to return a guest session, which was right
    // while the gate protected nothing — but the API now demands a token, so
    // a fabricated session would render the whole app against a backend
    // answering 401 to every request. Signing in again is the honest outcome.
    return null;
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

/**
 * A rough strength read-out, shown only while choosing a password.
 *
 * It scores length far above character variety, because length is what
 * actually costs an attacker time. Demanding a symbol mostly produces
 * "Passw0rd!", which is short, predictable and worse than three plain words.
 */
function scorePassword(password) {
  if (!password) return { level: 0, label: "" };

  let score = 0;
  if (password.length >= MIN_PASSWORD_LENGTH) score += 1;
  if (password.length >= 12) score += 1;
  if (password.length >= 16) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password) || /[^\w\s]/.test(password)) score += 1;

  // Anything with almost no distinct characters is weak whatever its length.
  if (new Set(password).size < 5) score = Math.min(score, 1);

  const level = Math.min(4, score);
  const labels = ["Too short", "Weak", "Okay", "Strong", "Very strong"];
  return { level, label: labels[level] };
}

export default function LoginPage({ onSignedIn }) {
  const [mode, setMode] = useState("signin"); // "signin" | "signup"

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [revealed, setRevealed] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [offerSignIn, setOfferSignIn] = useState(false);
  const [shaking, setShaking] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const emailRef = useRef(null);

  useEffect(() => {
    emailRef.current?.focus();
  }, [mode]);

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

  const strength = useMemo(
    () => (mode === "signup" ? scorePassword(password) : null),
    [mode, password]
  );

  function fail(message) {
    setError(message);
    setShaking(true);
    setTimeout(() => setShaking(false), 400);
  }

  function switchMode(next) {
    setMode(next);
    setError("");
    setOfferSignIn(false);
    setPassword("");
    setRevealed(false);
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError("");
    setOfferSignIn(false);

    try {
      const account =
        mode === "signup"
          ? await api.signUp({ email, password, name })
          : await api.signIn({ email, password });

      rememberSession(account);
      setLeaving(true);
      // Let the screen finish lifting away before the dashboard mounts.
      setTimeout(() => onSignedIn(account), 620);
    } catch (submitError) {
      setBusy(false);
      // 409: the address is registered. That is a wrong-tab mistake, not a
      // typo, so offer the fix instead of leaving them to work it out.
      if (submitError.status === 409) setOfferSignIn(true);
      fail(submitError.message);
    }
  }

  const signingUp = mode === "signup";
  const canSubmit =
    email.trim() !== "" &&
    password !== "" &&
    (!signingUp || password.length >= MIN_PASSWORD_LENGTH);

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
          </span>
        ))}
      </div>

      <form
        className={`lock-card ${shaking ? "shake" : ""}`}
        onSubmit={submit}
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
        <p className="lock-subtitle">
          {signingUp
            ? "Create an account to keep your dashboard behind a password."
            : "Welcome back. Sign in to open your dashboard."}
        </p>

        {/*
          Tabs rather than two separate screens. The sliding indicator is one
          element moved with a transform, so switching never reflows the card.
        */}
        <div className="mode-tabs" role="tablist" aria-label="Sign in or sign up">
          <span
            className="mode-indicator"
            style={{ transform: `translateX(${signingUp ? "100%" : "0%"})` }}
            aria-hidden="true"
          />
          <button
            type="button"
            role="tab"
            aria-selected={!signingUp}
            className={!signingUp ? "active" : ""}
            onClick={() => switchMode("signin")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={signingUp}
            className={signingUp ? "active" : ""}
            onClick={() => switchMode("signup")}
          >
            Create account
          </button>
        </div>

        {/* key={mode} restarts the entry animation, so switching tabs reads
            as a change rather than fields silently rewriting themselves. */}
        <div className="step stagger" key={mode}>
          {signingUp && (
            <div className="lock-field">
              <input
                id="name"
                type="text"
                autoComplete="name"
                value={name}
                placeholder=" "
                maxLength={60}
                onChange={(event) => setName(event.target.value)}
              />
              <label htmlFor="name">Your name (optional)</label>
            </div>
          )}

          <div className="lock-field">
            <input
              ref={emailRef}
              id="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="off"
              spellCheck="false"
              value={email}
              placeholder=" "
              maxLength={254}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(error)}
            />
            <label htmlFor="email">Email address</label>
          </div>

          <div className="lock-field password-field">
            <input
              id="password"
              type={revealed ? "text" : "password"}
              /* Telling the browser which one it is stops a password manager
                 offering to overwrite a saved password during sign-in. */
              autoComplete={signingUp ? "new-password" : "current-password"}
              value={password}
              placeholder=" "
              maxLength={128}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(error)}
            />
            <label htmlFor="password">Password</label>
            <button
              type="button"
              className="reveal"
              onClick={() => setRevealed((shown) => !shown)}
              aria-label={revealed ? "Hide password" : "Show password"}
              aria-pressed={revealed}
              tabIndex={-1}
            >
              {revealed ? "Hide" : "Show"}
            </button>
          </div>

          {signingUp && (
            <div className="strength" aria-live="polite">
              <div className="strength-track">
                {[0, 1, 2, 3].map((segment) => (
                  <span
                    key={segment}
                    className={
                      segment < strength.level
                        ? `on level-${strength.level}`
                        : ""
                    }
                  />
                ))}
              </div>
              <span className="strength-label">
                {password
                  ? strength.label
                  : `At least ${MIN_PASSWORD_LENGTH} characters`}
              </span>
            </div>
          )}

          <button className="lock-button" type="submit" disabled={busy || !canSubmit}>
            {busy ? (
              <>
                <span className="spinner" aria-hidden="true" />
                {signingUp ? "Creating account…" : "Signing in…"}
              </>
            ) : signingUp ? (
              "Create account"
            ) : (
              "Sign in"
            )}
          </button>

          <p className="lock-error" role="alert">
            {error}
            {offerSignIn && (
              <>
                {" "}
                <button
                  type="button"
                  className="link"
                  onClick={() => switchMode("signin")}
                >
                  Sign in
                </button>
              </>
            )}
          </p>

          <p className="mode-switch">
            {signingUp ? "Already have an account? " : "New here? "}
            <button
              type="button"
              className="link"
              onClick={() => switchMode(signingUp ? "signin" : "signup")}
            >
              {signingUp ? "Sign in" : "Create one"}
            </button>
          </p>
        </div>

        <p className="lock-disclosure">
          Your password is stored only as a salted PBKDF2 hash, never as text.
          Signing in still creates no session on the server, though — the API
          answers whether you sign in or not, and your transactions sit
          unencrypted in{" "}
          <span className="lock-hint">backend/data/expenses.db</span>.
        </p>
      </form>
    </div>
  );
}
