/**
 * The three things a screen shows when it has no content to show:
 * loading, nothing-yet, and something-broke.
 *
 * They live together because they are the same decision made three ways, and
 * a page that handles one but not the others is the page that shows a blank
 * rectangle to a user whose request failed.
 */

import { IconAlert, IconInbox } from "../../icons.jsx";
import Button from "./Button.jsx";

/** A grey block standing in for content that has not arrived. */
export function Skeleton({ width = "100%", height = 10, radius }) {
  return (
    <span
      className="skeleton"
      style={{
        display: "block",
        width,
        height,
        borderRadius: radius,
      }}
    />
  );
}

/**
 * Skeletons mirror the shape of what is coming, not a generic spinner. Four
 * stat cards resolve into four stat cards, so the layout does not jump when
 * the data lands.
 */
export function StatSkeleton({ count = 4 }) {
  return (
    <div className="grid-4">
      {Array.from({ length: count }, (_, index) => (
        <div className="card stat" key={index}>
          <div className="stat-top">
            <Skeleton width="72px" />
            <Skeleton width="30px" height={30} radius="var(--radius-sm)" />
          </div>
          <Skeleton width="60%" height={26} />
          <Skeleton width="45%" height={9} />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6 }) {
  return (
    <div className="card">
      <div className="card-head bordered">
        <Skeleton width="140px" height={14} />
      </div>
      <div className="card-body">
        {Array.from({ length: rows }, (_, index) => (
          <div
            key={index}
            style={{
              display: "flex",
              gap: "var(--sp-4)",
              alignItems: "center",
              padding: "var(--sp-3) 0",
            }}
          >
            <Skeleton width="80px" />
            <Skeleton width="40%" />
            <Skeleton width="90px" />
            <Skeleton width="70px" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChartSkeleton({ height = 260 }) {
  return (
    <div className="card">
      <div className="card-head">
        <Skeleton width="150px" height={14} />
      </div>
      <div className="card-body">
        <Skeleton height={height} radius="var(--radius)" />
      </div>
    </div>
  );
}

/**
 * Nothing here yet — and, crucially, the way out.
 *
 * An empty state without an action is a dead end: it tells someone the app is
 * working correctly and leaves them with nothing to do about it.
 */
export function EmptyState({
  icon: Icon = IconInbox,
  title,
  description,
  action,
}) {
  return (
    <div className="state">
      <div className="state-icon">
        <Icon size={20} />
      </div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div className="state-actions">{action}</div>}
    </div>
  );
}

/**
 * Something failed.
 *
 * The user gets a sentence they can act on; the backend's own words go to the
 * console for whoever is debugging. Showing a raw 500 to someone trying to
 * read their spending helps nobody, but hiding it from the developer helps
 * nobody either.
 */
export function ErrorState({ title = "Something went wrong", error, onRetry }) {
  if (error) {
    console.error("[expense-tracker]", error);
  }

  return (
    <div className="state">
      <div className="state-icon danger">
        <IconAlert size={20} />
      </div>
      <h3>{title}</h3>
      <p>
        {error?.message ||
          "We could not load this right now. Please try again."}
      </p>
      {onRetry && (
        <div className="state-actions">
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
