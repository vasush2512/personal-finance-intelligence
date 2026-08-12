import { useEffect, useMemo, useRef, useState } from "react";

import "../login.css";

/**
 * The lock screen.
 *
 * Read this before judging it: it is a presentation surface, not security.
 * There is no account, no server-side session and no encryption. Anyone with
 * the machine can open backend/data/expenses.db and read everything, and the
 * API answers every request whether this screen was passed or not.
 *
 * The screen says so itself rather than implying a protection it does not
 * provide. A login box that looks like a lock but is not one teaches the
 * person using it the wrong thing about their own data.
 *
 * PRD section 3 lists accounts and authentication as non-goals; this exists
 * because it was asked for, and is deliberately the smallest thing that can
 * be called a login screen.
 */

const PASSCODE = "demo";
const STORAGE_KEY = "expense-tracker-unlocked";

/** Thematic drifting chips: the app's own subject matter, not confetti. */
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

/** True if this browser tab has already been unlocked. */
export function isUnlocked() {
  try {
    return sessionStorage.getItem(STORAGE_KEY) === "yes";
  } catch {
    // Private browsing can make sessionStorage throw. Failing open is right:
    // this gate protects nothing, so it must never lock someone out.
    return true;
  }
}

export function lock() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to clean up */
  }
}

function remember() {
  try {
    sessionStorage.setItem(STORAGE_KEY, "yes");
  } catch {
    /* the gate simply reappears next time */
  }
}

export default function LoginPage({ onUnlock }) {
  const [passcode, setPasscode] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [shaking, setShaking] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /**
   * Positions and timings are chosen once and kept.
   *
   * Recomputing them on every render would make every chip jump to a new
   * place and restart its animation each time a key is pressed.
   */
  const chips = useMemo(
    () =>
      CHIPS.map((chip, index) => {
        // Two bands down the sides, leaving the middle clear for the card.
        // Alternating rather than random keeps the two sides balanced.
        const onLeft = index % 2 === 0;
        const offset = ((index * 7) % 18) - 9; // -9%..+9% of spread
        return {
          ...chip,
          left: `${(onLeft ? 16 : 84) + offset}%`,
          duration: `${17 + ((index * 3.1) % 11)}s`,
          // Negative delays start each chip partway through its loop, so the
          // screen is already populated on the first frame instead of empty.
          delay: `${-(index * 2.3).toFixed(1)}s`,
        };
      }),
    []
  );

  function submit(event) {
    event.preventDefault();
    if (checking || leaving) return;

    setChecking(true);
    setError("");

    // A short pause so the button's loading state is visible rather than
    // flickering. There is nothing to wait for — nothing is being verified
    // against anything.
    setTimeout(() => {
      if (passcode.trim().toLowerCase() === PASSCODE) {
        remember();
        setLeaving(true);
        // Let the screen finish lifting away before the dashboard mounts.
        setTimeout(onUnlock, 620);
        return;
      }

      setChecking(false);
      setError(`That is not the passcode. It is "${PASSCODE}".`);
      setShaking(true);
      setTimeout(() => setShaking(false), 400);
      inputRef.current?.select();
    }, 480);
  }

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
        onSubmit={submit}
        aria-labelledby="lock-title"
      >
        <div className="stagger">
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
            Bank statements in. Categorized spending, monthly trends and
            unusual charges out.
          </p>

          <div className="lock-field">
            <input
              ref={inputRef}
              id="passcode"
              type="password"
              value={passcode}
              placeholder=" "
              autoComplete="off"
              spellCheck="false"
              onChange={(event) => setPasscode(event.target.value)}
              aria-describedby="lock-disclosure"
              aria-invalid={Boolean(error)}
            />
            <label htmlFor="passcode">Passcode</label>
          </div>

          <button className="lock-button" type="submit" disabled={checking}>
            {checking ? (
              <>
                <span className="spinner" aria-hidden="true" />
                Opening…
              </>
            ) : (
              "Open dashboard"
            )}
          </button>

          <p className="lock-error" role="alert">
            {error}
          </p>
        </div>

        <p className="lock-disclosure" id="lock-disclosure">
          The passcode is <span className="lock-hint">demo</span>. This screen
          is presentation only — it is not security. There is no account and no
          session on the server; the API answers whether you pass this screen
          or not, and your transactions sit unencrypted in{" "}
          <span className="lock-hint">backend/data/expenses.db</span>.
        </p>
      </form>
    </div>
  );
}
