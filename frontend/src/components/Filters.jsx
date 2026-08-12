import { formatCategory, formatMonth } from "../format.js";

/**
 * One row of filters above the table.
 *
 * Every option here is built from what is actually in the database, not from
 * a fixed list: months come from the trend data, categories from the
 * category breakdown, and sources from the files and worksheets that were
 * imported. An option you can pick always has rows behind it.
 *
 * The one deliberate exception is the table's own category dropdown, which
 * offers all twelve — you have to be able to move a row to a category that
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
    // A file selected whole has no sheet part. A workbook tab does. The
    // empty string is meaningful — it means "rows with no worksheet".
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
}) {
  function update(key, value) {
    onChange({ ...filters, [key]: value });
  }

  const isFiltered =
    filters.month || filters.category || filters.source || searchValue;

  // Only worth showing when there is more than one place rows came from.
  const showSource =
    sources.length > 1 || (sources[0] && sources[0].sheets.length > 1);

  return (
    <div className="filters">
      {showSource && (
        <div className="field">
          <label htmlFor="source">Source</label>
          <select
            id="source"
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

      <div className="field">
        <label htmlFor="month">Month</label>
        <select
          id="month"
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
        <label htmlFor="search">Search</label>
        {/* Typing here does not refetch on every keystroke — App debounces it. */}
        <input
          id="search"
          type="search"
          placeholder="swiggy, rent, amazon…"
          value={searchValue}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>

      {isFiltered && (
        <div className="field">
          <label>&nbsp;</label>
          <button onClick={onReset}>Clear filters</button>
        </div>
      )}
    </div>
  );
}
