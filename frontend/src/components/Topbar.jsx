import { useEffect, useRef, useState } from "react";

import { IconLogOut, IconMenu, IconSettings } from "../icons.jsx";
import { formatMonth } from "../format.js";
import { navigate } from "../router.js";
import Button from "./ui/Button.jsx";

/**
 * Page title, the period selector, and the account menu.
 *
 * The month selector lives up here rather than on each page because it scopes
 * everything below it — the cards, the charts and the table all read the same
 * filter, so a control that belonged to one of them would imply the others
 * were unaffected.
 */
import StatementPicker from "./StatementPicker.jsx";

export default function Topbar({
  title,
  description,
  months,
  month,
  onMonthChange,
  showMonth,
  sources = [],
  source,
  onSourceChange,
  onAddTransaction,
  session,
  onSignOut,
  onOpenSidebar,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  // A menu that stays open when you click elsewhere is a menu you have to
  // dismiss twice.
  useEffect(() => {
    if (!menuOpen) return undefined;

    function onDocumentClick(event) {
      if (!menuRef.current?.contains(event.target)) setMenuOpen(false);
    }
    function onKeyDown(event) {
      if (event.key === "Escape") setMenuOpen(false);
    }

    document.addEventListener("mousedown", onDocumentClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocumentClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const initials = (session?.display_name || session?.email || "?")
    .slice(0, 2)
    .toUpperCase();

  return (
    <header className="topbar">
      <Button
        variant="ghost"
        className="menu-button"
        onClick={onOpenSidebar}
        aria-label="Open navigation"
        aria-controls="sidebar"
        icon={IconMenu}
      />

      <div className="topbar-titles">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>

      <div className="topbar-actions">
        {/* Which statement everything on screen is about. In the topbar rather
            than on one page, because it scopes every page — see
            StatementPicker for the full reasoning. */}
        {/* Reachable from every page: recording a cash expense should not
            start with navigating somewhere. */}
        {onAddTransaction && (
          <Button
            size="sm"
            variant="primary"
            onClick={onAddTransaction}
            title="Record a transaction by hand"
          >
            + Add
          </Button>
        )}

        {onSourceChange && (
          <StatementPicker
            sources={sources}
            value={source}
            onChange={onSourceChange}
          />
        )}
        {showMonth && months.length > 0 && (
          <>
            <label className="visually-hidden" htmlFor="period">
              Period
            </label>
            <select
              id="period"
              className="select select-sm"
              style={{ width: "auto" }}
              value={month || ""}
              onChange={(event) => onMonthChange(event.target.value)}
            >
              <option value="">All time</option>
              {months.map((value) => (
                <option key={value} value={value}>
                  {formatMonth(value)}
                </option>
              ))}
            </select>
          </>
        )}

        <div ref={menuRef} style={{ position: "relative" }}>
          <button
            className="account"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
          >
            <span className="avatar">{initials}</span>
            <span className="account-name">
              {session?.display_name || "Account"}
            </span>
          </button>

          {menuOpen && (
            <div className="menu" role="menu">
              <div className="menu-head">
                <strong>{session?.display_name}</strong>
                <span>{session?.email}</span>
              </div>
              <button
                className="menu-item"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/settings");
                }}
              >
                <IconSettings size={15} />
                Settings
              </button>
              <button className="menu-item" role="menuitem" onClick={onSignOut}>
                <IconLogOut size={15} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
