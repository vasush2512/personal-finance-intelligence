/**
 * Display helpers.
 *
 * The API sends money as a string like "9400.00" on purpose. Turning it into
 * a Number is fine for drawing a bar whose height is approximate anyway, but
 * every number the user *reads* is formatted from the original string, so
 * nothing is ever shown that floating point has rounded.
 */

/** "9400.00" -> "₹9,400" with Indian digit grouping. */
export function formatMoney(amount) {
  const number = Number(amount);
  if (Number.isNaN(number)) return "₹0";
  return `₹${number.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

/** "9400.00" -> "₹9,400.00", for the table where exactness matters. */
export function formatMoneyExact(amount) {
  const [whole, fraction = "00"] = String(amount).split(".");
  const grouped = Number(whole).toLocaleString("en-IN");
  return `₹${grouped}.${fraction}`;
}

/** For charts only. */
export function toNumber(amount) {
  const number = Number(amount);
  return Number.isNaN(number) ? 0 : number;
}

/** "2026-05" -> "May 2026" */
export function formatMonth(month) {
  const [year, monthNumber] = month.split("-");
  const date = new Date(Number(year), Number(monthNumber) - 1, 1);
  return date.toLocaleString("en-IN", { month: "short", year: "numeric" });
}

/** "2026-08-06" -> "6 Aug 2026" */
export function formatDate(isoDate) {
  const date = new Date(`${isoDate}T00:00:00`);
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "bills_utilities" -> "Bills & utilities" */
export function formatCategory(category) {
  if (category === "bills_utilities") return "Bills & utilities";
  return category.charAt(0).toUpperCase() + category.slice(1);
}

/**
 * Bank narrations are long and noisy. Show enough to recognise the row.
 */
export function shortenDescription(description, maxLength = 52) {
  if (description.length <= maxLength) return description;
  return `${description.slice(0, maxLength - 1)}…`;
}
