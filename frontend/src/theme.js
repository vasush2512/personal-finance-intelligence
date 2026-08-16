import { useEffect, useState } from "react";

import { THEME_CHANGE_EVENT } from "./theme-mode.js";

/**
 * Chart colours, read from the CSS tokens at runtime.
 *
 * Recharts takes real colour values, not `var(--primary)` — an SVG `fill` of
 * a custom property does resolve, but the tooltip and label props are plain
 * strings that never touch the DOM, so half a chart would follow the theme and
 * half would not.
 *
 * So instead of keeping a second palette in JavaScript, this reads the
 * variables back out of the document. styles.css stays the single source of
 * truth, and a theme switch needs no change here at all.
 *
 * Only two categorical slots are used, because only two series ever appear
 * together in this app (spent vs income). The category breakdown is drawn as
 * ranked bars in a single hue rather than a twelve-colour donut: about eight
 * hues stay separable for colourblind readers, and past that a palette becomes
 * a rainbow that encodes nothing.
 */

function token(styles, name, fallback) {
  return styles.getPropertyValue(name).trim() || fallback;
}

/** Snapshot the current palette. Cheap — one getComputedStyle per change. */
export function readChartTheme() {
  // Guard for any environment without a live CSSOM — server rendering, a test
  // harness, jsdom without a stylesheet. Checking for getComputedStyle rather
  // than for `document` is the load-bearing part: a stub document is common,
  // and only this call actually needs the browser.
  if (typeof document === "undefined" || typeof getComputedStyle !== "function") {
    return {
      series: { spent: "#2563eb", income: "#059669" },
      magnitude: "#2563eb",
      chrome: {
        grid: "#e5e7eb",
        axis: "#d1d5db",
        muted: "#94a3b8",
        secondary: "#475569",
        surface: "#ffffff",
      },
      tooltip: {},
      cursor: { fill: "rgba(15, 23, 42, 0.04)" },
    };
  }

  const styles = getComputedStyle(document.documentElement);
  const dark = document.documentElement.getAttribute("data-theme") === "dark";

  const grid = token(styles, "--border", "#e5e7eb");
  const surface = token(styles, "--surface", "#ffffff");

  return {
    series: {
      spent: token(styles, "--primary", "#2563eb"),
      income: token(styles, "--success", "#059669"),
    },
    magnitude: token(styles, "--primary", "#2563eb"),
    chrome: {
      grid,
      axis: token(styles, "--border-strong", "#d1d5db"),
      muted: token(styles, "--text-muted", "#94a3b8"),
      secondary: token(styles, "--text-secondary", "#475569"),
      surface,
    },
    tooltip: {
      background: surface,
      borderRadius: 10,
      border: `1px solid ${grid}`,
      boxShadow: dark
        ? "0 10px 24px rgba(0, 0, 0, 0.5)"
        : "0 10px 24px rgba(15, 23, 42, 0.08)",
      fontSize: 12.5,
      padding: "8px 12px",
      color: token(styles, "--text", "#0f172a"),
    },
    // The hover band behind a bar. White at low opacity on dark, ink on light —
    // the same 4% wash either way, which is why it cannot be one colour.
    cursor: {
      fill: dark ? "rgba(255, 255, 255, 0.06)" : "rgba(15, 23, 42, 0.04)",
    },
  };
}

/**
 * The palette, kept in step with the theme.
 *
 * Re-reads on the event theme-mode.js fires, so switching to dark repaints
 * every chart without a reload and without any chart knowing why.
 */
export function useChartTheme() {
  const [theme, setTheme] = useState(readChartTheme);

  useEffect(() => {
    const onChange = () => setTheme(readChartTheme());
    window.addEventListener(THEME_CHANGE_EVENT, onChange);
    return () => window.removeEventListener(THEME_CHANGE_EVENT, onChange);
  }, []);

  return theme;
}
