/**
 * The four states the application's financial data can be in (§2).
 *
 * These were previously implicit — spread across `loading`, `loadError`,
 * `uploading` and `summary === null`, and worked out afresh by each page.
 * Four booleans describe sixteen combinations, most of which cannot happen,
 * and the ones that can were being read differently in different places.
 *
 * Naming the states makes the impossible ones unrepresentable and gives every
 * page one question to ask instead of four.
 *
 *   NO_STATEMENT      signed in, nothing uploaded — every figure is zero
 *   PROCESSING        a file is being parsed, categorised and analysed
 *   STATEMENT_LOADED  there is data, and it is what the pages render
 *   ERROR             the data could not be loaded or the upload failed
 *
 * NO_STATEMENT is deliberately not an error and not a loading state. It is a
 * correct, complete answer — the app is working, and there is nothing there.
 */

export const NO_STATEMENT = "NO_STATEMENT";
export const PROCESSING = "PROCESSING";
export const STATEMENT_LOADED = "STATEMENT_LOADED";
export const ERROR = "ERROR";

/**
 * Work out the current state from what the shell knows.
 *
 * Order matters and encodes precedence:
 *   - an upload in flight outranks everything, because the dashboard behind it
 *     is about to be replaced anyway;
 *   - an error only counts while there is no data to fall back on — a failed
 *     background refresh must not blank a working page;
 *   - "no statement" is decided by the transaction count, not by the absence
 *     of a response, so a successful empty response is not mistaken for a
 *     failed one.
 */
export function resolveDataState({ uploading, loading, error, summary }) {
  if (uploading) return PROCESSING;
  if (error && !summary) return ERROR;
  if (loading && !summary) return PROCESSING;
  if (!summary || summary.transaction_count === 0) return NO_STATEMENT;
  return STATEMENT_LOADED;
}

/** Whether financial figures may be shown at all. */
export function hasFinancialData(state) {
  return state === STATEMENT_LOADED;
}

/**
 * The zeroed summary a page renders when there is no statement.
 *
 * Returned as real zeros rather than nulls so the cards render "₹0" instead of
 * an em dash: with no statement the honest answer is zero, not unknown. Every
 * list is empty, so nothing downstream can find a figure to display.
 */
export function emptySummary() {
  return {
    total_spent: "0.00",
    total_income: "0.00",
    net: "0.00",
    transaction_count: 0,
    by_category: [],
    by_category_source: [],
    top_merchants: [],
  };
}
