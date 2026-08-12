import { useCallback, useEffect, useState } from "react";

import * as api from "./api.js";
import CategoryChart from "./components/CategoryChart.jsx";
import Filters from "./components/Filters.jsx";
import SummaryCards from "./components/SummaryCards.jsx";
import Toast from "./components/Toast.jsx";
import TopMerchants from "./components/TopMerchants.jsx";
import TransactionTable, { PAGE_SIZE } from "./components/TransactionTable.jsx";
import TrendChart from "./components/TrendChart.jsx";
import UploadBox from "./components/UploadBox.jsx";
import { formatMonth } from "./format.js";

const EMPTY_FILTERS = { month: "", category: "", search: "" };

export default function App() {
  const [categories, setCategories] = useState([]);
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState([]);
  const [page, setPage] = useState({ items: [], total: 0 });

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);

  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [lastUpload, setLastUpload] = useState(null);
  const [toast, setToast] = useState(null);

  function showError(error) {
    setToast({ kind: "error", message: error.message });
  }

  function showSuccess(message) {
    setToast({ kind: "success", message });
  }

  /** The category vocabulary is fetched once; it never changes at runtime. */
  useEffect(() => {
    api.getCategories().then(setCategories).catch(showError);
  }, []);

  /**
   * Everything the dashboard shows, reloaded together.
   *
   * The three requests go out in parallel: they do not depend on each other,
   * and running them in sequence would make the page feel three times slower
   * than it is.
   */
  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryData, trendData, pageData] = await Promise.all([
        api.getSummary(filters.month),
        api.getTrends(),
        api.getTransactions({ ...filters, limit: PAGE_SIZE, offset }),
      ]);
      setSummary(summaryData);
      setTrends(trendData);
      setPage(pageData);
    } catch (error) {
      showError(error);
    } finally {
      setLoading(false);
    }
  }, [filters, offset]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  async function handleUpload(file) {
    setUploading(true);
    try {
      const result = await api.uploadStatement(file);
      setLastUpload(result);
      setOffset(0);
      await loadDashboard();
      if (result.imported > 0) {
        showSuccess(`Imported ${result.imported} transactions.`);
      }
    } catch (error) {
      showError(error);
    } finally {
      setUploading(false);
    }
  }

  async function handleCategoryChange(id, category) {
    setSavingId(id);
    try {
      const updated = await api.updateCategory(id, category);
      // Patch the row in place so the table does not jump while you work,
      // then refresh the totals, which have changed underneath it.
      setPage((current) => ({
        ...current,
        items: current.items.map((row) => (row.id === id ? updated : row)),
      }));
      const summaryData = await api.getSummary(filters.month);
      setSummary(summaryData);
    } catch (error) {
      showError(error);
    } finally {
      setSavingId(null);
    }
  }

  function changeFilters(next) {
    setFilters(next);
    setOffset(0);
  }

  const months = trends.map((point) => point.month).reverse();
  const hasData = summary && summary.transaction_count > 0;
  const isFirstLoad = loading && !summary;

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>Expense Tracker</h1>
          <p>Upload a bank statement. Everything is categorized automatically.</p>
        </div>
        {hasData && (
          <p>
            {page.total} transactions
            {filters.month ? ` in ${formatMonth(filters.month)}` : " tracked"}
          </p>
        )}
      </header>

      <div className="stack">
        <UploadBox onUpload={handleUpload} busy={uploading} lastResult={lastUpload} />

        {isFirstLoad && <p className="loading">Loading…</p>}

        {!isFirstLoad && !hasData && (
          <div className="card empty">
            <h2>No transactions yet</h2>
            <p>
              Upload a statement CSV above to get started. There is a sample at
              <br />
              <code>backend/data/sample_statement.csv</code>
            </p>
          </div>
        )}

        {hasData && (
          <>
            <SummaryCards
              summary={summary}
              scopeLabel={filters.month ? formatMonth(filters.month) : "All time"}
            />

            <TrendChart trends={trends} />

            <div className="grid-2">
              <CategoryChart
                categories={summary.by_category}
                selected={filters.category}
                onSelect={(category) =>
                  changeFilters({
                    ...filters,
                    category: filters.category === category ? "" : category,
                  })
                }
              />
              <TopMerchants merchants={summary.top_merchants} />
            </div>

            <div className="card">
              <Filters
                filters={filters}
                months={months}
                categories={categories}
                onChange={changeFilters}
                onReset={() => changeFilters(EMPTY_FILTERS)}
              />
            </div>

            {loading ? (
              <p className="loading">Loading transactions…</p>
            ) : (
              <TransactionTable
                page={page}
                categories={categories}
                onChangeCategory={handleCategoryChange}
                savingId={savingId}
                offset={offset}
                onOffsetChange={setOffset}
              />
            )}
          </>
        )}
      </div>

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
