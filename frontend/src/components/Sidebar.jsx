import { IconWallet } from "../icons.jsx";
import { ROUTES } from "../router.js";

/**
 * The primary navigation.
 *
 * Links are real anchors to real hash URLs, so middle-click, "open in new tab"
 * and the browser's own history all work without any of it being reimplemented
 * in JavaScript.
 *
 * On a narrow screen this becomes a drawer rather than a squeezed column — see
 * the 900px breakpoint in styles.css. `open` slides it in; the parent renders
 * the scrim behind it.
 */
export default function Sidebar({ route, counts = {}, open, onNavigate }) {
  // Grouped by the `group` field on each route, in the order they appear, so
  // adding a route to router.js is the only edit needed to see it here.
  // Routes marked hidden are real destinations reached from a button rather
  // than from the nav — listing them here would be a second door to the same
  // room.
  const groups = ROUTES.filter((entry) => !entry.hidden).reduce((acc, entry) => {
    (acc[entry.group] = acc[entry.group] || []).push(entry);
    return acc;
  }, {});

  return (
    <aside className={`sidebar ${open ? "open" : ""}`} id="sidebar">
      <div className="brand">
        <span className="brand-mark">
          <IconWallet size={17} />
        </span>
        <div>
          <div className="brand-name">Expense Tracker</div>
          <div className="brand-sub">Statement analytics</div>
        </div>
      </div>

      <nav className="nav" aria-label="Main">
        {Object.entries(groups).map(([group, entries]) => (
          <div key={group}>
            <div className="nav-section">{group}</div>
            {entries.map(({ path, label, icon: Icon }) => {
              const active = route === path;
              const count = counts[path];

              return (
                <a
                  key={path}
                  href={`#${path}`}
                  className={`nav-link ${active ? "active" : ""}`}
                  // The styling already shows which page you are on; this is
                  // the same fact for a screen reader, which cannot see it.
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                >
                  <Icon size={16} />
                  {label}
                  {count > 0 && <span className="nav-count">{count}</span>}
                </a>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        Rules and a classifier label every row. You can correct any of them.
      </div>
    </aside>
  );
}
