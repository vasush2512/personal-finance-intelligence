/**
 * Chart colors.
 *
 * Two series appear together anywhere in this app (spent vs income), so only
 * the first two categorical slots are used. The category breakdown is drawn
 * as ranked bars in a single hue rather than a 12-colour donut: eight is the
 * most hues that stay separable for colourblind readers, and past that a
 * palette becomes a rainbow that encodes nothing.
 *
 * Slot order and hex values come from the validated reference palette.
 */

export const SERIES = {
  spent: "#2a78d6", // categorical slot 1, blue
  income: "#eb6834", // categorical slot 2, orange
};

/** Single hue for magnitude-only charts. */
export const MAGNITUDE = "#2a78d6";

export const CHROME = {
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
  secondary: "#52514e",
  surface: "#fcfcfb",
};
