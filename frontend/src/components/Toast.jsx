import { useEffect } from "react";

/**
 * A single message pinned to the corner.
 *
 * Failed uploads show the backend's own words — "Could not find a header row
 * with a date and a description column. Columns found: random, junk" tells
 * the user what to fix; "Upload failed" does not.
 *
 * Success messages clear themselves. Errors stay until dismissed, because an
 * error you looked away from is one you never read.
 */
const SUCCESS_TIMEOUT_MS = 4000;

export default function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast || toast.kind !== "success") return undefined;
    const timer = setTimeout(onDismiss, SUCCESS_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  return (
    <div className={`toast ${toast.kind}`} role="status">
      <span>{toast.message}</span>
      <button onClick={onDismiss} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}
