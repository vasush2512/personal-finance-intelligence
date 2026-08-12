import { ROUTES } from "../router.js";

/**
 * The page switcher.
 *
 * Real anchors rather than buttons, so the browser's own affordances work:
 * middle-click, copy link, back button, and a URL that survives a refresh.
 */
export default function NavBar({ route, counts }) {
  return (
    <nav className="nav" aria-label="Sections">
      {ROUTES.map((entry) => (
        <a
          key={entry.path}
          href={`#${entry.path}`}
          className={`nav-link ${route === entry.path ? "active" : ""}`}
          aria-current={route === entry.path ? "page" : undefined}
        >
          {entry.label}
          {counts[entry.path] > 0 && (
            <span className="nav-count">{counts[entry.path]}</span>
          )}
        </a>
      ))}
    </nav>
  );
}
