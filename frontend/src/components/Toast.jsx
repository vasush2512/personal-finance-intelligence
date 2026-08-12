/**
 * A single message pinned to the corner.
 *
 * Failed uploads show the backend's own words — "Could not find a header row
 * with a date and a description column. Columns found: random, junk" tells
 * the user what to fix; "Upload failed" does not.
 */
export default function Toast({ toast, onDismiss }) {
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
