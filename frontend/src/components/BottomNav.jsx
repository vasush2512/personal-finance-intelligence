import { ROUTES } from "../router.js";

/**
 * Phone navigation (§28).
 *
 * A drawer is the right pattern for eleven destinations, but it costs a tap
 * before you can go anywhere, and on a phone the four places people actually
 * move between deserve to be one tap. So both exist: this bar for the common
 * routes, the drawer behind the menu button for everything else.
 *
 * Hidden above the phone breakpoint by CSS rather than by a JS media query, so
 * there is no flash of the wrong navigation on first paint and no resize
 * listener to keep in step.
 */
const PRIMARY = ["/", "/transactions", "/analytics", "/upload"];

export default function BottomNav({ route, onOpenMore }) {
  const entries = PRIMARY.map((path) =>
    ROUTES.find((entry) => entry.path === path)
  ).filter(Boolean);

  return (
    <nav className="bottom-nav" aria-label="Primary">
      {entries.map(({ path, label, icon: Icon }) => {
        const active = route === path;
        return (
          <a
            key={path}
            href={`#${path}`}
            className={`bottom-link ${active ? "active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={19} />
            <span>{label === "Upload Statement" ? "Upload" : label}</span>
          </a>
        );
      })}

      <button type="button" className="bottom-link" onClick={onOpenMore}>
        <span className="bottom-more" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span>More</span>
      </button>
    </nav>
  );
}
