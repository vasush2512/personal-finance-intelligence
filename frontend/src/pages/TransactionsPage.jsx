import ExportMenu from "../components/ExportMenu.jsx";
import Filters, { decodeSource } from "../components/Filters.jsx";
import TransactionTable from "../components/TransactionTable.jsx";
import Card, { CardHead } from "../components/ui/Card.jsx";

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
  onOpen,
  onError,
  onSuccess,
  tags = [],
  accounts = [],
  paymentMethods = [],
}) {
  const isFiltered = Boolean(
    filters.month ||
      filters.category ||
      filters.source ||
      filters.direction ||
      searchInput
  );

  return (
    <div className="stack">
      <Card>
        <CardHead
          title="Filters"
          description="Every option is built from what is actually in your data"
          actions={
            <ExportMenu
              // `source` is the dropdown's encoded "3::June"; the API takes
              // upload_id and sheet, exactly as every other call does.
              params={{
                month: filters.month,
                category: filters.category,
                direction: filters.direction,
                search: searchInput,
                ...decodeSource(filters.source),
              }}
              scopeLabel={
                isFiltered
                  ? "Downloads the filtered rows"
                  : `Downloads all ${page.total.toLocaleString("en-IN")} rows`
              }
              onError={onError}
              onSuccess={onSuccess}
            />
          }
        />
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
          tags={tags}
          accounts={accounts}
          paymentMethods={paymentMethods}
        />
      </Card>

      {/* The table stays mounted while refetching. Swapping it for a skeleton
          on every filter change makes the page flash and loses your scroll
          position — so it dims instead, which reads as "updating" rather than
          "gone". */}
      <div
        style={{
          opacity: loading ? 0.55 : 1,
          transition: "opacity var(--fast) var(--ease)",
        }}
        aria-busy={loading}
      >
        <TransactionTable
          page={page}
          categories={categories}
          onChangeCategory={onChangeCategory}
          savingId={savingId}
          offset={offset}
          onOffsetChange={onOffsetChange}
          onClearFilters={onReset}
          isFiltered={isFiltered}
          onOpen={onOpen}
        />
      </div>
    </div>
  );
}
