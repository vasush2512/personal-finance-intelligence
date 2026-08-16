import { useEffect } from "react";

import { IconAlert, IconCheckCircle, IconInfo, IconX } from "../icons.jsx";

/**
 * A single message pinned to the corner.
 *
 * Failed uploads show the backend's own words — "Could not find a header row
 * with a date and a description column. Columns found: random, junk" tells the
 * user what to fix; "Upload failed" does not.
 *
 * Success messages clear themselves. Errors and explanations stay until
 * dismissed, because a message you looked away from is one you never read —
 * and "nothing happened, here is why" is exactly the message a user needs to
 * finish reading.
 *
 * role="status" rather than "alert": this is announced politely, after the
 * screen reader finishes its current sentence, instead of interrupting.
 */
const SUCCESS_TIMEOUT_MS = 4000;

const ICONS = {
  success: IconCheckCircle,
  error: IconAlert,
  info: IconInfo,
};

export default function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast || toast.kind !== "success") return undefined;
    const timer = setTimeout(onDismiss, SUCCESS_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  const Icon = ICONS[toast.kind] || IconInfo;

  return (
    <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
      <span className="toast-icon">
        <Icon size={17} />
      </span>
      <p>{toast.message}</p>
      <button
        className="btn btn-ghost btn-sm btn-icon"
        onClick={onDismiss}
        aria-label="Dismiss notification"
      >
        <IconX size={14} />
      </button>
    </div>
  );
}
