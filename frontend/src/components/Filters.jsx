import { formatCategory, formatMonth } from "../format.js";
import { PRESETS } from "../datePresets.js";
import { IconSearch, IconX } from "../icons.jsx";
import Button from "./ui/Button.jsx";

/**
 * The filter row above the table.
 *
 * Every option here is built from what is actually in the database, not from a
 * fixed list: months come from the trend data, categories from the category
 * breakdown, and sources from the files and worksheets that were imported. An
 * option you can pick always has rows behind it.
 *
 * The one deliberate exception is the table's own category dropdown, which
 * offers all twelve — you have to be able to move a row into a category that
 * is currently empty.
 */

/** Source filter values encode file and sheet: "3" or "3::June". */
export function encodeSource(uploadId, sheetName) {
  if (uploadId === null || uploadId === undefined) return "";
  if (sheetName === null || sheetName === undefined) return String(uploadId);
  return `${uploadId}::${sheetName}`;
}

export function decodeSource(value) {
  if (!value) return { upload_id: undefined, sheet: undefined };

  const [uploadId, ...rest] = value.split("::");
  return {
    upload_id: Number(uploadId),
    // A file selected whole has no sheet part. A workbook tab does. The empty
    // string is meaningful — it means "rows with no worksheet".
    sheet: rest.length > 0 ? rest.join("::") : undefined,
  };
}

export default function Filters({
  filters,
  months,
  categories,
  sources,
  searchValue,
  onSearchChange,
  onChange,
  onReset,
  tags = [],
  accounts = [],
  paymentMethods = [],
}) {
  function update(key, value) {
    onChange({ ...filters, [key]: value });
  }

  const isFiltered = Boolean(
    filters.month ||
      filters.category ||
      filters.source ||
      filters.direction ||
      filters.entry_source ||
      filters.tag ||
      filters.datePreset ||
      filters.account ||
      filters.payment_method ||
      filters.min_amount ||
      filters.max_amount ||
      searchValue
  );

  // Only worth showing when there is more than one place rows came from — but
  // always while one is selected, or the filter scoping the page would have no
  // visible control.
  const showSource =
    Boolean(filters.source) ||
    sources.length > 1 ||
    (sources[0] && sources[0].sheets.length > 1);

  return (
    <div className="card-body">
      <div className="filters">
        <div className="field search-field">
          <label htmlFor="search">Search</label>
          <IconSearch size={14} style={{ top: "calc(50% + 9px)" }} />
          {/* Typing here does not refetch on every keystroke — App debounces. */}
          <input
            id="search"
            className="input"
            type="search"
            placeholder="swiggy, rent, amazon…"
            value={searchValue}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="month">Month</label>
          <select
            id="month"
            className="select"
            value={filters.month || ""}
            onChange={(event) => update("month", event.target.value)}
          >
            <option value="">All time</option>
            {months.map((month) => (
              <option key={month} value={month}>
                {formatMonth(month)}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="category">Category</label>
          <select
            id="category"
            className="select"
            value={filters.category || ""}
            onChange={(event) => update("category", event.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((entry) => (
              <option key={entry.category} value={entry.category}>
                {formatCategory(entry.category)} ({entry.count})
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="date-preset">Period</label>
          <select
            id="date-preset"
            className="select"
            value={filters.datePreset || ""}
            onChange={(event) => update("datePreset", event.target.value)}
          >
            {PRESETS.map((preset) => (
              <option key={preset.value} value={preset.value}>
                {preset.label}
              </option>
            ))}
          </select>
        </div>

        {filters.datePreset === "custom" && (
          <>
            <div className="field">
              <label htmlFor="date-from">From</label>
              <input
                id="date-from"
                type="date"
                className="input"
                value={filters.dateFrom || ""}
                onChange={(event) => update("dateFrom", event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="date-to">To</label>
              <input
                id="date-to"
                type="date"
                className="input"
                value={filters.dateTo || ""}
                onChange={(event) => update("dateTo", event.target.value)}
              />
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor="direction">Type</label>
          <select
            id="direction"
            className="select"
            value={filters.direction || ""}
            onChange={(event) => update("direction", event.target.value)}
          >
            <option value="">Money in and out</option>
            <option value="debit">Money out</option>
            <option value="credit">Money in</option>
          </select>
        </div>

        {/* Where a row came from. Both are the same kind of transaction and
            are shown together by default; this is here so "what did I type in
            myself?" can be asked without the app keeping two sets of books. */}
        <div className="field">
          <label htmlFor="entry-source">Entered by</label>
          <select
            id="entry-source"
            className="select"
            value={filters.entry_source || ""}
            onChange={(event) => update("entry_source", event.target.value)}
          >
            <option value="">Statements and manual</option>
            <option value="statement">From a statement</option>
            <option value="manual">Added by hand</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="min-amount">Amount</label>
          <div className="range-pair">
            <input
              id="min-amount"
              className="input"
              value={filters.min_amount || ""}
              onChange={(event) => update("min_amount", event.target.value)}
              placeholder="Min"
              inputMode="decimal"
            />
            <input
              className="input"
              value={filters.max_amount || ""}
              onChange={(event) => update("max_amount", event.target.value)}
              placeholder="Max"
              inputMode="decimal"
              aria-label="Maximum amount"
            />
          </div>
        </div>

        {/* Offered only once there is more than one account to choose between,
            for the same reason the source-file filter is. */}
        {accounts.filter((entry) => entry.id !== null).length > 1 && (
          <div className="field">
            <label htmlFor="account">Account</label>
            <select
              id="account"
              className="select"
              value={filters.account || ""}
              onChange={(event) => update("account", event.target.value)}
            >
              <option value="">Every account</option>
              {accounts
                .filter((entry) => entry.id !== null)
                .map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.name} ({entry.transaction_count.toLocaleString("en-IN")})
                  </option>
                ))}
            </select>
          </div>
        )}

        {paymentMethods.length > 0 && (
          <div className="field">
            <label htmlFor="payment-method">Paid by</label>
            <select
              id="payment-method"
              className="select"
              value={filters.payment_method || ""}
              onChange={(event) => update("payment_method", event.target.value)}
            >
              <option value="">Any method</option>
              {paymentMethods.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Only offered once tags exist. An empty dropdown teaches nothing. */}
        {tags.length > 0 && (
          <div className="field">
            <label htmlFor="tag">Tag</label>
            <select
              id="tag"
              className="select"
              value={filters.tag || ""}
              onChange={(event) => update("tag", event.target.value)}
            >
              <option value="">Any tag</option>
              {tags.map((entry) => (
                <option key={entry.id} value={entry.name}>
                  #{entry.name} ({entry.count})
                </option>
              ))}
            </select>
          </div>
        )}

        {showSource && (
          <div className="field">
            <label htmlFor="source">Source file</label>
            <select
              id="source"
              className="select"
              value={filters.source || ""}
              onChange={(event) => update("source", event.target.value)}
            >
              <option value="">All sources</option>
              {sources.map((source) => (
                <optgroup key={source.upload_id} label={source.filename}>
                  <option value={encodeSource(source.upload_id)}>
                    Whole file ({source.count})
                  </option>
                  {source.sheets
                    .filter((sheet) => sheet.sheet_name)
                    .map((sheet) => (
                      <option
                        key={sheet.sheet_name}
                        value={encodeSource(source.upload_id, sheet.sheet_name)}
                      >
                        {sheet.sheet_name} ({sheet.count})
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </div>
        )}

        {isFiltered && (
          <div className="field">
            <label aria-hidden="true">&nbsp;</label>
            <Button variant="ghost" icon={IconX} onClick={onReset}>
              Clear filters
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
