/**
 * The date ranges people actually ask for, resolved to real dates.
 *
 * A month dropdown answers "how much in June". It cannot answer "this week",
 * "the last three months", or "between these two dates" — which is most of
 * what someone wants when they are looking for a particular transaction.
 *
 * Every preset resolves to an explicit from/to pair before it reaches the API,
 * so the backend has one thing to implement rather than a vocabulary of names
 * it would have to keep in step with this file.
 */

export const PRESETS = [
  { value: "", label: "Any date" },
  { value: "today", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "3m", label: "Last 3 months" },
  { value: "6m", label: "Last 6 months" },
  { value: "year", label: "This year" },
  { value: "custom", label: "Custom range…" },
];

function iso(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * A preset name -> {date_from, date_to}, or null for "any date"/"custom".
 *
 * `today` is a parameter rather than read from the clock inside, so this is
 * testable and so a page rendered at 23:59 cannot disagree with itself a
 * minute later.
 */
export function resolvePreset(preset, today = new Date()) {
  const start = new Date(today);
  const end = new Date(today);

  switch (preset) {
    case "today":
      return { date_from: iso(start), date_to: iso(end) };

    case "week": {
      // Monday as the first day: an Indian statement week is not a US one,
      // and "this week" on a Sunday should not mean "one day".
      const weekday = (start.getDay() + 6) % 7;
      start.setDate(start.getDate() - weekday);
      return { date_from: iso(start), date_to: iso(end) };
    }

    case "month":
      start.setDate(1);
      return { date_from: iso(start), date_to: iso(end) };

    case "last_month": {
      const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      // Day 0 of this month is the last day of the previous one, which avoids
      // having to know how long February is.
      const last = new Date(today.getFullYear(), today.getMonth(), 0);
      return { date_from: iso(first), date_to: iso(last) };
    }

    case "3m":
      start.setMonth(start.getMonth() - 3);
      return { date_from: iso(start), date_to: iso(end) };

    case "6m":
      start.setMonth(start.getMonth() - 6);
      return { date_from: iso(start), date_to: iso(end) };

    case "year":
      return { date_from: `${today.getFullYear()}-01-01`, date_to: iso(end) };

    default:
      return null;
  }
}

/**
 * The filter object -> the query the API expects.
 *
 * Kept here rather than in each page so the table, the export and anything
 * added later cannot resolve the same preset to different dates.
 */
export function dateQuery(filters, today = new Date()) {
  if (filters.datePreset === "custom") {
    return {
      date_from: filters.dateFrom || undefined,
      date_to: filters.dateTo || undefined,
    };
  }

  const resolved = resolvePreset(filters.datePreset, today);
  return resolved || {};
}
