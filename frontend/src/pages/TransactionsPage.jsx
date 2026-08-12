import Filters from "../components/Filters.jsx";
import TransactionTable from "../components/TransactionTable.jsx";

/** The list, and everything for narrowing it. */
export default function TransactionsPage({
  page,
  categories,
  sources,
  months,
  filters,
  searchInput,
  onSearchChange,
  onFilterChange,
  onReset,
  onChangeCategory,
  savingId,
  offset,
  onOffsetChange,
  loading,
}) {
  return (
    <>
      <div className="card">
        <Filters
          filters={filters}
          months={months}
          // Only categories that have rows. Offering an option that can only
          // ever return "no transactions match" is noise.
          categories={categories.filter((entry) => entry.count > 0)}
          sources={sources}
          searchValue={searchInput}
          onSearchChange={onSearchChange}
          onChange={onFilterChange}
          onReset={onReset}
        />
      </div>

      {/* The table stays mounted while refetching. Swapping it for a spinner
          on every filter change makes the page flash and loses your scroll
          position. */}
      <div style={{ opacity: loading ? 0.55 : 1, transition: "opacity .15s" }}>
        <TransactionTable
          page={page}
          categories={categories}
          onChangeCategory={onChangeCategory}
          savingId={savingId}
          offset={offset}
          onOffsetChange={onOffsetChange}
        />
      </div>
    </>
  );
}
