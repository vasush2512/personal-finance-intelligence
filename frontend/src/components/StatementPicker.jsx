import { decodeSource, encodeSource } from "./Filters.jsx";
import { IconFile } from "../icons.jsx";

/**
 * Which statement the whole app is looking at.
 *
 * This used to live only on the Transactions page, which made it a filter on a
 * table rather than what it actually is: the scope of every number on every
 * screen. Someone who picked a file on Transactions and then opened Data
 * Quality had no way to tell what the report was about, and no way to change
 * it without navigating back.
 *
 * So it sits in the topbar, visible everywhere, and reads as a selection
 * rather than a filter — "All statements" is a choice, not the absence of one.
 *
 * Worksheets inside a workbook are offered as their own options: a file with a
 * tab per month is several statements in one upload, and the app can scope to
 * one of them.
 */
export default function StatementPicker({ sources, value, onChange }) {
  // Nothing to choose between until there is more than one place rows came
  // from — but always shown while a selection is active, or the control that
  // scoped the page would be invisible.
  const options = [];
  sources.forEach((source) => {
    options.push({
      value: encodeSource(source.upload_id),
      label: source.filename,
      count: source.count,
    });

    // Defensive: a source without a sheets array is not something this API
    // returns, but a crash here takes the whole topbar — and with it every
    // page — down with it.
    const sheets = source.sheets || [];
    if (sheets.length > 1) {
      sheets.forEach((sheet) => {
        options.push({
          value: encodeSource(source.upload_id, sheet.sheet_name ?? ""),
          label: `    ${source.filename} › ${sheet.sheet_name || "main"}`,
          count: sheet.count,
        });
      });
    }
  });

  if (options.length <= 1 && !value) return null;

  const total = sources.reduce((sum, source) => sum + source.count, 0);
  const selected = value ? decodeSource(value) : null;

  return (
    <label className="statement-picker">
      <IconFile size={14} />
      <span className="visually-hidden">Statement</span>
      <select
        className="select select-sm"
        value={value || ""}
        onChange={(event) => onChange(event.target.value)}
        title={
          selected
            ? "Every page is showing this statement only"
            : "Every page is showing all your statements together"
        }
      >
        <option value="">
          All statements ({total.toLocaleString("en-IN")})
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label} ({option.count.toLocaleString("en-IN")})
          </option>
        ))}
      </select>
    </label>
  );
}
