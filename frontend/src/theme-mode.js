import { useEffect, useState } from "react";

/**
 * Light / dark / system, stored in the browser.
 *
 * Three options rather than a two-way switch. "System" is the honest default —
 * someone whose laptop turns dark at sunset expects this to follow, and a
 * binary toggle forces them to pick a side and then re-pick it twice a day.
 *
 * The resolved value ("light" or "dark") is written to `data-theme` on <html>,
 * which is the single switch every CSS token hangs off. Nothing else in the
 * app needs to know which theme is active — including the charts, which read
 * the resolved CSS variables rather than keeping their own copy.
 *
 * index.html applies the same resolution before first paint. That duplication
 * is deliberate: an import would make it async, and async means a white flash.
 */

const STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export const MODES = ["light", "dark", "system"];

/** Fires whenever the resolved theme changes, so charts can re-read colours. */
export const THEME_CHANGE_EVENT = "themechange";

function readStoredMode() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return MODES.includes(stored) ? stored : "system";
  } catch {
    // Private browsing throws on localStorage. Fall back rather than fail.
    return "system";
  }
}

function systemPrefersDark() {
  return window.matchMedia(DARK_QUERY).matches;
}

/** "system" -> whatever the OS currently says. */
export function resolveMode(mode) {
  if (mode === "light" || mode === "dark") return mode;
  return systemPrefersDark() ? "dark" : "light";
}

function apply(mode) {
  const resolved = resolveMode(mode);
  document.documentElement.setAttribute("data-theme", resolved);
  // Let the native form controls and scrollbars match the palette too.
  document.documentElement.style.colorScheme = resolved;
  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: resolved }));
  return resolved;
}

/**
 * The theme control's state.
 *
 * Returns the chosen mode (which may be "system") and the resolved one, since
 * the UI needs both: the segmented control highlights the choice, while a
 * label can say what "system" currently amounts to.
 */
export function useThemeMode() {
  const [mode, setMode] = useState(readStoredMode);
  const [resolved, setResolved] = useState(() => resolveMode(readStoredMode()));

  useEffect(() => {
    setResolved(apply(mode));

    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // Preference just will not persist. The theme still applies this session.
    }
  }, [mode]);

  // Follow the OS while the choice is "system" — and only then, or an explicit
  // choice would be overridden the next time the laptop switched at sunset.
  useEffect(() => {
    if (mode !== "system") return undefined;

    const query = window.matchMedia(DARK_QUERY);
    const onChange = () => setResolved(apply("system"));
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [mode]);

  return { mode, resolved, setMode };
}
