import { formatCategory, formatMonth } from "../format.js";

/**
 * One row of filters above the table: month, category, and a text search.
 */
export default function Filters({
  filters,
  months,
  categories,
  searchValue,
  onSearchChange,
  onChange,
  onReset,
}) {
  function update(key, value) {
    onChange({ ...filters, [key]: value });
  }

  const isFiltered = filters.month || filters.category || searchValue;

  return (
    <div className="filters">
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
          {categories.map((category) => (
            <option key={category} value={category}>
              {formatCategory(category)}
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
