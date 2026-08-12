import { useCallback, useEffect, useState } from "react";

import * as api from "./api.js";
import NavBar from "./components/NavBar.jsx";
import Toast from "./components/Toast.jsx";
import { decodeSource, encodeSource } from "./components/Filters.jsx";
import { PAGE_SIZE } from "./components/TransactionTable.jsx";
import { formatMonth } from "./format.js";
import FilesPage from "./pages/FilesPage.jsx";
import LoginPage, { clearSession, currentSession } from "./pages/LoginPage.jsx";
import ModelPage from "./pages/ModelPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import TransactionsPage from "./pages/TransactionsPage.jsx";
import UnusualPage from "./pages/UnusualPage.jsx";
import { navigate, useRoute } from "./router.js";

const EMPTY_FILTERS = { month: "", category: "", search: "", source: "" };
const SEARCH_DEBOUNCE_MS = 300;

/**
 * The shell. It owns the data and the filters; the pages only render.
 *
 * One place fetches, so the filters cannot mean different things on
 * different pages — pick a category on Overview and the Transactions page is
 * already narrowed to it when you arrive.
 */
export default function App() {
  const route = useRoute();

  // Presentation only — see LoginPage. Nothing behind this is protected, so
  // the gate lives entirely in the browser and never gates a request.
  const [session, setSession] = useState(currentSession);
  const unlocked = Boolean(session);

  const [categories, setCategories] = useState([]);
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [sources, setSources] = useState([]);
  const [page, setPage] = useState({ items: [], total: 0 });

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  // What is in the search box, which is not yet what has been searched for.
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);

  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [lastUpload, setLastUpload] = useState(null);
  const [toast, setToast] = useState(null);

  function showError(error) {
    setToast({ kind: "error", message: error.message });
  }

  function showSuccess(message) {
    setToast({ kind: "success", message });
  }

  function showInfo(message) {
    setToast({ kind: "info", message });
  }

  /**
   * Everything the dashboard shows, reloaded together.
   *
   * The requests go out in parallel: they do not depend on each other, and
   * running them in sequence would make the page feel several times slower
   * than it is.
   */
  const loadDashboard = useCallback(async () => {
    // Nothing to show behind the lock screen, so do not go and fetch it.
    if (!unlocked) return;

    setLoading(true);
    try {
      // The source filter travels as upload_id + sheet, not as the single
      // value the dropdown uses, so unpack it before it reaches the API.
      const { source, ...rest } = filters;
      const sourceQuery = decodeSource(source);

      const transactionQuery = {
        ...rest,
        ...sourceQuery,
        limit: PAGE_SIZE,
        offset,
      };

      const [summaryData, trendData, anomalyData, sourceData, categoryData, pageData] =
        await Promise.all([
          // Source reaches the cards, the charts and the anomalies too. A
          // filter that moved only the table would leave the totals above it
          // describing a different set of transactions.
          api.getSummary({ month: filters.month, ...sourceQuery }),
          api.getTrends(sourceQuery),
          api.getAnomalies(sourceQuery),
          api.getSources(),
          api.getCategories(),
          api.getTransactions(transactionQuery),
        ]);

      setSummary(summaryData);
      setTrends(trendData);
      setAnomalies(anomalyData);
      setSources(sourceData);
      setCategories(categoryData);
      setPage(pageData);
    } catch (error) {
      showError(error);
    } finally {
      setLoading(false);
    }
  }, [filters, offset, unlocked]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  /**
   * Wait until typing pauses before searching.
   *
   * Without this, "swiggy" fires six requests and the table flashes six
   * times. The timer resets on every keystroke, so only the pause triggers.
   */
  useEffect(() => {
    if (searchInput === filters.search) return undefined;
    const timer = setTimeout(() => {
      setFilters((current) => ({ ...current, search: searchInput }));
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput, filters.search]);

  /**
   * Import a batch of files, then refresh once.
   *
   * Sequential rather than parallel on purpose: imports race on the same
   * fingerprint table, and two files sharing a transaction could both think
   * theirs is new. One at a time makes the duplicate counts honest.
   *
   * A file that fails does not abort the batch — the other statements still
   * import, and the failure is named in the summary.
   */
  async function handleUpload(files) {
    setUploading(true);
    const totals = { imported: 0, duplicates: 0, skipped: 0, files: 0, failures: [] };
    const results = [];

    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        setUploadProgress({
          current: index + 1,
          total: files.length,
          filename: file.name,
        });

        try {
          const result = await api.uploadStatement(file);
          results.push(result);
          totals.imported += result.imported;
          totals.duplicates += result.duplicates;
          totals.skipped += result.skipped;
          totals.files += 1;
        } catch (error) {
          totals.failures.push({ filename: file.name, message: error.message });
        }
      }

      setLastUpload(totals);
      setOffset(0);

      // Show what was just added rather than leaving it buried in the whole
      // database. Importing 29 rows into 100,000 moves nothing visible, and
      // the upload reads as having failed.
      //
      // Only when a single file actually contributed rows: scoping to one of
      // several would hide the others, and an upload that imported nothing
      // has no rows to scope to.
      const imported = results.filter((result) => result && result.imported > 0);
      if (imported.length === 1) {
        setFilters({ ...EMPTY_FILTERS, source: encodeSource(imported[0].upload_id) });
        setSearchInput("");
        navigate("/");
      } else {
        await loadDashboard();
      }

      if (totals.imported > 0) {
        showSuccess(`Imported ${totals.imported} transactions.`);
      } else if (totals.files > 0 && totals.duplicates > 0) {
        // The commonest confusion in this app: a correct no-op looks broken.
        // Say plainly that the upload worked and why nothing moved.
        showInfo(
          `Already imported. All ${totals.duplicates} rows were recognised as ` +
            `duplicates, so nothing changed. Upload a statement for a different ` +
            `period to add to your data.`
        );
      }
      if (totals.failures.length > 0) {
        showError(
          new Error(
            `${totals.failures.length} file(s) could not be imported. See the details above the summary.`
          )
        );
      }
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }

  async function handleCategoryChange(id, category) {
    setSavingId(id);
    try {
      const updated = await api.updateCategory(id, category);

      if (filters.category) {
        // A category filter is on, so the row you just re-labelled probably
        // no longer belongs in this list. Reload rather than leave it there
        // contradicting the filter above it.
        await loadDashboard();
      } else {
        // Patch in place so the table does not jump while you work, then
        // refresh the totals, which have changed underneath it.
        setPage((current) => ({
          ...current,
          items: current.items.map((row) => (row.id === id ? updated : row)),
        }));
        const { source, ...rest } = filters;
        setSummary(
          await api.getSummary({ month: rest.month, ...decodeSource(source) })
        );
      }
    } catch (error) {
      showError(error);
    } finally {
      setSavingId(null);
    }
  }

  async function handleDeleteUpload(uploadId, filename) {
    try {
      const result = await api.deleteUpload(uploadId);
      // The filter may have been pointing at what was just deleted.
      setFilters(EMPTY_FILTERS);
      setSearchInput("");
      setOffset(0);
      showSuccess(
        `Deleted ${filename} and its ${result.transactions_deleted.toLocaleString(
          "en-IN"
        )} transactions.`
      );
    } catch (error) {
      showError(error);
    }
  }

  function changeFilters(next) {
    setFilters(next);
    setSearchInput(next.search || "");
    setOffset(0);
  }

  /** "september_2026.csv" or "book.xlsx › June", when a source is selected. */
  const scope = (() => {
    if (!filters.source) return null;
    const { upload_id, sheet } = decodeSource(filters.source);
    const source = sources.find((entry) => entry.upload_id === upload_id);
    if (!source) return null;
    return sheet ? `${source.filename} › ${sheet}` : source.filename;
  })();

  const months = trends.map((point) => point.month).reverse();
  const hasData = summary && summary.transaction_count > 0;
  const isFirstLoad = loading && !summary;

  const navCounts = {
    "/unusual": anomalies.length,
    "/files": sources.length,
  };

  /**
   * Sign out. Local, because the session is local.
   *
   * The server call only drops a half-finished code, so a sign-in that was
   * abandoned mid-way cannot be resumed afterwards. It is fire-and-forget:
   * a failure there must not leave someone stuck signed in.
   */
  function handleSignOut() {
    if (session?.phone) api.signOut(session.phone).catch(() => {});
    clearSession();
    setSession(null);
    setFilters(EMPTY_FILTERS);
    setSearchInput("");
    setOffset(0);
  }

  if (!unlocked) {
    return <LoginPage onSignedIn={setSession} />;
  }

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>Expense Tracker</h1>
          <p>Upload a bank statement. Everything is categorized automatically.</p>
        </div>
        <div className="masthead-right">
          {hasData && (
            <p>
              {summary.transaction_count.toLocaleString("en-IN")} transactions
              {filters.month ? ` in ${formatMonth(filters.month)}` : " tracked"}
            </p>
          )}
          <div className="account">
            <span className="account-phone">{session.display_phone}</span>
            <button className="lock-again" onClick={handleSignOut}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <NavBar route={route} counts={navCounts} />

      <div className="stack">
        {isFirstLoad && <p className="loading">Loading…</p>}

        {/* The page is scoped to one file or tab. Say so where the numbers
            are — otherwise scoped totals look like totals for everything. */}
        {scope && (
          <div className="card scope-banner">
            <span>
              Showing <strong>{scope}</strong> only. The totals, charts and
              anomalies below cover just this.
            </span>
            <button onClick={() => changeFilters(EMPTY_FILTERS)}>
              Show everything
            </button>
          </div>
        )}

        {!isFirstLoad && !hasData && route !== "/files" && (
          <div className="card empty">
            <h2>No transactions yet</h2>
            <p>
              Go to <a href="#/files">Files</a> and upload a statement. There is
              a sample at <code>backend/data/sample_statement.csv</code>.
            </p>
          </div>
        )}

        {route === "/files" && (
          <FilesPage
            sources={sources}
            onUpload={handleUpload}
            uploading={uploading}
            uploadProgress={uploadProgress}
            lastUpload={lastUpload}
            onDelete={handleDeleteUpload}
            filters={filters}
            onFilterChange={changeFilters}
          />
        )}

        {hasData && route === "/" && (
          <OverviewPage
            summary={summary}
            trends={trends}
            filters={filters}
            onFilterChange={changeFilters}
          />
        )}

        {hasData && route === "/transactions" && (
          <TransactionsPage
            page={page}
            categories={categories}
            sources={sources}
            months={months}
            filters={filters}
            searchInput={searchInput}
            onSearchChange={setSearchInput}
            onFilterChange={changeFilters}
            onReset={() => changeFilters(EMPTY_FILTERS)}
            onChangeCategory={handleCategoryChange}
            savingId={savingId}
            offset={offset}
            onOffsetChange={setOffset}
            loading={loading}
          />
        )}

        {hasData && route === "/unusual" && <UnusualPage anomalies={anomalies} />}

        {hasData && route === "/model" && (
          <ModelPage
            summary={summary}
            onRetrained={loadDashboard}
            onError={showError}
          />
        )}
      </div>

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
