import { useCallback, useEffect, useState } from "react";

import * as api from "./api.js";
import BottomNav from "./components/BottomNav.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Topbar from "./components/Topbar.jsx";
import Toast from "./components/Toast.jsx";
import TransactionDrawer from "./components/TransactionDrawer.jsx";
import { decodeSource, encodeSource } from "./components/Filters.jsx";
import { PAGE_SIZE } from "./components/TransactionTable.jsx";
import Button from "./components/ui/Button.jsx";
import {
  ChartSkeleton,
  EmptyState,
  ErrorState,
  StatSkeleton,
  TableSkeleton,
} from "./components/ui/Feedback.jsx";
import { IconUpload } from "./icons.jsx";
import { formatMonth } from "./format.js";
import { dateQuery } from "./datePresets.js";
import {
  ERROR,
  NO_STATEMENT,
  PROCESSING,
  hasFinancialData,
  resolveDataState,
} from "./dataState.js";
import AnalyticsPage from "./pages/AnalyticsPage.jsx";
import CategoriesPage from "./pages/CategoriesPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import AccountsPage from "./pages/AccountsPage.jsx";
import PersonalExpensesPage from "./pages/PersonalExpensesPage.jsx";
import AddTransactionPage from "./pages/AddTransactionPage.jsx";
import AskPage from "./pages/AskPage.jsx";
import BudgetsPage from "./pages/BudgetsPage.jsx";
import RulesPage from "./pages/RulesPage.jsx";
import DataQualityPage from "./pages/DataQualityPage.jsx";
import ReportPage from "./pages/ReportPage.jsx";
import DuplicatesPage from "./pages/DuplicatesPage.jsx";
import ForecastPage from "./pages/ForecastPage.jsx";
import RecurringPage from "./pages/RecurringPage.jsx";
import LoginPage, { clearSession, currentSession } from "./pages/LoginPage.jsx";
import ModelPage from "./pages/ModelPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import TransactionsPage from "./pages/TransactionsPage.jsx";
import UnusualPage from "./pages/UnusualPage.jsx";
import UploadPage from "./pages/UploadPage.jsx";
import { navigate, routeMeta, useRoute } from "./router.js";

const EMPTY_FILTERS = {
  month: "",
  category: "",
  search: "",
  direction: "",
  source: "",
  // Where a row came from, and any tag on it. Both reach the API through the
  // same query the table already sends.
  entry_source: "",
  tag: "",
  // Period. The preset resolves to a real from/to pair in datePresets.js, so
  // the backend only ever sees explicit dates.
  datePreset: "",
  dateFrom: "",
  dateTo: "",
  account: "",
  payment_method: "",
  min_amount: "",
  max_amount: "",
};
const SEARCH_DEBOUNCE_MS = 300;

/** Kept in step with PAYMENT_METHODS in the backend constants. */
const PAYMENT_METHODS = [
  "Cash", "UPI", "Card", "Credit Card", "Debit Card", "Net banking",
  "NEFT", "IMPS", "Wallet", "Cheque", "Auto-debit", "Other",
];

/** Pages that mean something before any data exists. */
const WORKS_WHEN_EMPTY = new Set([
  "/upload", "/settings", "/categories", "/quality", "/rules", "/accounts",
  "/personal", "/budgets", "/add",
]);

/**
 * The shell. It owns the data and the filters; the pages only render.
 *
 * One place fetches, so the filters cannot mean different things on different
 * pages — pick a category on the dashboard and the Transactions page is
 * already narrowed to it when you arrive.
 */
export default function App() {
  const route = useRoute();
  const meta = routeMeta(route);

  // The account is real; the gate is not. Nothing behind this is protected, so
  // it lives entirely in the browser and never gates a request. See LoginPage
  // for the full statement of that.
  const [session, setSession] = useState(currentSession);
  const unlocked = Boolean(session);

  const [categories, setCategories] = useState([]);
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [sources, setSources] = useState([]);
  const [health, setHealth] = useState(null);
  const [page, setPage] = useState({ items: [], total: 0 });

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  // What is in the search box, which is not yet what has been searched for.
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [lastUpload, setLastUpload] = useState(null);
  const [toast, setToast] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Which transaction the detail drawer is showing, if any.
  const [openTransactionId, setOpenTransactionId] = useState(null);

  /**
   * Bumped whenever the underlying data changes — an upload, a correction, a
   * rule applied, a statement deleted.
   *
   * The dashboard reloads itself, but the heavy panels (duplicates, forecast,
   * model, data quality, report) each load their own data once on arrival.
   * Without a signal like this they keep showing figures from before the
   * upload until the page is revisited, which reads as the upload not having
   * worked.
   */
  const [dataVersion, setDataVersion] = useState(0);

  // The full category vocabulary — built-in plus the user's own — and their
  // accounts. Both are needed by the add form wherever it opens, so they are
  // loaded by the shell rather than by whichever page happens to be showing.
  const [categoryChoices, setCategoryChoices] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [tags, setTags] = useState([]);


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

      // The preset becomes real dates here, once, so the table and anything
      // else reading these filters cannot resolve it differently.
      const { datePreset, dateFrom, dateTo, account, ...plain } = rest;

      const transactionQuery = {
        ...plain,
        ...sourceQuery,
        ...dateQuery({ datePreset, dateFrom, dateTo }),
        account_id: account || undefined,
        limit: PAGE_SIZE,
        offset,
      };

      const [
        summaryData,
        trendData,
        anomalyData,
        sourceData,
        categoryData,
        pageData,
        choicesData,
        accountsData,
        tagsData,
        healthData,
      ] =
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
          // Scored over all months, so it deliberately ignores the month
          // filter — a health score for one month is a different, weaker
          // claim than one built on the whole history.
          //
          // Caught rather than allowed to reject: health is one card, and
          // Promise.all fails the whole batch on any single rejection. An
          // older backend without this endpoint would otherwise blank the
          // entire dashboard, which is exactly what it did the first time.
          // Caught for the same reason health is: neither is worth blanking
          // the dashboard over.
          api.getCategoryChoices().catch(() => []),
          api.getAccounts().catch(() => []),
          api.getTags().catch(() => []),
          api.getFinancialHealth(sourceQuery).catch((error) => ({
            available: false,
            components: [],
            reason:
              error.status === 404
                ? "This backend does not provide a health score yet. Restart it to pick up the latest version."
                : "Could not load the health score.",
          })),
        ]);

      setSummary(summaryData);
      setTrends(trendData);
      setAnomalies(anomalyData);
      setSources(sourceData);
      setCategories(categoryData);
      setPage(pageData);
      setCategoryChoices(choicesData);
      setAccounts(accountsData);
      setTags(tagsData);
      setHealth(healthData);
      setLoadError(null);
    } catch (error) {
      // A failed first load has no data to fall back on, so the page shows an
      // error state rather than an empty one — "you have no transactions" is
      // the wrong thing to tell someone whose backend is down.
      setLoadError(error);
      showError(error);
    } finally {
      setLoading(false);
    }
  }, [filters, offset, unlocked]);

  /**
   * Reload the dashboard AND tell every self-loading panel to refetch.
   *
   * Declared after loadDashboard, not before: a useCallback dependency array
   * is evaluated during render, so naming a `const` declared further down
   * throws before React can paint anything. That is a blank screen, not a
   * warning — which is exactly what it did.
   */
  const refreshEverything = useCallback(async () => {
    setDataVersion((version) => version + 1);
    await loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  /**
   * Confirm the stored token is still good, with the server.
   *
   * The browser remembering an account is not evidence of anything now — the
   * token can have expired, or been signed out from another tab. Asking is
   * cheap and is the difference between a working app and every panel showing
   * an authentication error.
   */
  useEffect(() => {
    if (!session) return;
    api.whoAmI().then((account) => {
      if (!account) {
        clearSession();
        setSession(null);
      }
    });
    // Once, on mount: a token that goes stale mid-session surfaces as a 401
    // on the next request, which the error state already handles.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Wait until typing pauses before searching.
   *
   * Without this, "swiggy" fires six requests and the table flashes six times.
   * The timer resets on every keystroke, so only the pause triggers.
   */
  useEffect(() => {
    if (searchInput === filters.search) return undefined;
    const timer = setTimeout(() => {
      setFilters((current) => ({ ...current, search: searchInput }));
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput, filters.search]);

  // Moving to another page closes the mobile drawer. Leaving it open over the
  // new page is the commonest bug in a slide-out nav.
  useEffect(() => {
    setSidebarOpen(false);
  }, [route]);

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
      // several would hide the others, and an upload that imported nothing has
      // no rows to scope to.
      const imported = results.filter((result) => result && result.imported > 0);
      if (imported.length === 1) {
        // Changing the filter reloads the dashboard by itself; the panels that
        // load their own data need telling separately.
        setFilters({ ...EMPTY_FILTERS, source: encodeSource(imported[0].upload_id) });
        setSearchInput("");
        setDataVersion((version) => version + 1);
      } else {
        await refreshEverything();
      }

      if (totals.imported > 0) {
        showSuccess(`Imported ${totals.imported.toLocaleString("en-IN")} transactions.`);
      } else if (totals.files > 0 && totals.duplicates > 0) {
        // The commonest confusion in this app: a correct no-op looks broken.
        // Say plainly that the upload worked and why nothing moved.
        showInfo(
          `Already imported. All ${totals.duplicates.toLocaleString("en-IN")} rows ` +
            `were recognised as duplicates, so nothing changed. Upload a statement ` +
            `for a different period to add to your data.`
        );
      }
      if (totals.failures.length > 0) {
        showError(
          new Error(
            `${totals.failures.length} file(s) could not be imported. See the details above.`
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
        // A category filter is on, so the row you just re-labelled probably no
        // longer belongs in this list. Reload rather than leave it there
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
      showSuccess("Category updated.");
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
      throw error;
    }
  }

  function changeFilters(next) {
    setFilters(next);
    setSearchInput(next.search || "");
    setOffset(0);
  }

  function selectCategory(category) {
    changeFilters({ ...EMPTY_FILTERS, category });
    navigate("/transactions");
  }

  /**
   * Sign out. Local, because the session is local.
   *
   * The server call is fire-and-forget — there is nothing on that side to end,
   * and a failure there must never leave someone stuck signed in.
   */
  function handleSignOut() {
    api.signOut().catch(() => {});
    clearSession();
    setSession(null);
    setFilters(EMPTY_FILTERS);
    setSearchInput("");
    setOffset(0);
  }

  if (!unlocked) {
    return <LoginPage onSignedIn={setSession} />;
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

  // §2: one named state, derived once, instead of four booleans each page
  // re-interprets. See dataState.js for what each means and why.
  const dataState = resolveDataState({ uploading, loading, error: loadError, summary });
  const hasData = hasFinancialData(dataState);
  const scopeLabel = filters.month ? formatMonth(filters.month) : "All time";

  const navCounts = { "/unusual": anomalies.length, "/upload": sources.length };

  return (
    <div className="shell">
      {sidebarOpen && (
        <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />
      )}

      <Sidebar
        route={route}
        counts={navCounts}
        open={sidebarOpen}
        onNavigate={() => setSidebarOpen(false)}
      />

      <div className="main">
        <Topbar
          title={meta.title}
          description={meta.description}
          months={months}
          month={filters.month}
          onMonthChange={(month) => changeFilters({ ...filters, month })}
          // The period selector only belongs where it changes something.
          showMonth={hasData && ["/", "/analytics", "/forecast", "/budgets"].includes(route)}
          sources={sources}
          source={filters.source}
          onSourceChange={(next) => changeFilters({ ...filters, source: next })}
          onAddTransaction={() => navigate("/add")}
          session={session}
          onSignOut={handleSignOut}
          onOpenSidebar={() => setSidebarOpen(true)}
        />

        <main className="content">
          <div className="stack">
            {/* The page is scoped to one file or tab. Say so where the numbers
                are — otherwise scoped totals look like totals for everything. */}
            {scope && (
              <div className="banner">
                <span>
                  Showing <strong>{scope}</strong> only. Totals, charts and
                  anomalies below cover just this file.
                </span>
                <span className="banner-actions">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => changeFilters(EMPTY_FILTERS)}
                  >
                    Show everything
                  </Button>
                </span>
              </div>
            )}

            {renderRoute()}
          </div>
        </main>
      </div>

      <BottomNav route={route} onOpenMore={() => setSidebarOpen(true)} />

      <TransactionDrawer
        transactionId={openTransactionId}
        categories={categories}
        savingId={savingId}
        onClose={() => setOpenTransactionId(null)}
        onChangeCategory={handleCategoryChange}
      />

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );

  function renderRoute() {
    // Skeletons shaped like what is coming, so the layout does not jump.
    if (dataState === PROCESSING && !summary) {
      return (
        <>
          <StatSkeleton />
          <ChartSkeleton />
          <TableSkeleton />
        </>
      );
    }

    if (dataState === ERROR) {
      return (
        <div className="card">
          <ErrorState
            title="We couldn't load your data"
            error={loadError}
            onRetry={loadDashboard}
          />
        </div>
      );
    }

    // Pages that manage data still work with none of it; the rest would just be
    // a grid of zeroes, so they get the empty state and a way out instead.
    if (dataState === NO_STATEMENT && !WORKS_WHEN_EMPTY.has(route)) {
      return (
        <div className="card">
          <EmptyState
            icon={IconUpload}
            title="No transactions yet"
            description="Upload your bank statement to start analysing your financial activity. There is a sample at backend/data/sample_statement.csv."
            action={
              <Button variant="primary" onClick={() => navigate("/upload")}>
                Upload statement
              </Button>
            }
          />
        </div>
      );
    }

    switch (route) {
      case "/transactions":
        return (
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
            tags={tags}
            accounts={accounts}
            paymentMethods={PAYMENT_METHODS}
            onChangeCategory={handleCategoryChange}
            savingId={savingId}
            offset={offset}
            onOffsetChange={setOffset}
            loading={loading}
            onOpen={setOpenTransactionId}
            onError={showError}
            onSuccess={showSuccess}
          />
        );

      case "/analytics":
        return (
          <AnalyticsPage
            summary={summary}
            trends={trends}
            scopeLabel={scopeLabel}
            month={filters.month}
            source={filters.source}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
          />
        );

      case "/unusual":
        return <UnusualPage anomalies={anomalies} />;

      // Both of these scan a two-year window and load their own data on
      // arrival — see useResource.js for why they are not in the batch above.
      case "/report":
        return (
          <ReportPage
            source={filters.source}
            month={filters.month}
            dataVersion={dataVersion}
            session={session}
          />
        );

      case "/budgets":
        return (
          <BudgetsPage
            choices={categoryChoices}
            month={filters.month}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onChanged={refreshEverything}
          />
        );

      case "/add":
        return (
          <AddTransactionPage
            categories={categoryChoices}
            accounts={accounts}
            onSaved={async (created) => {
              // Refresh first, so the list on the page behind is already
              // showing the new row when navigation lands there.
              await refreshEverything();
              showSuccess(`Added ${created.merchant || "transaction"}.`);
            }}
            onError={showError}
          />
        );

      case "/personal":
        return (
          <PersonalExpensesPage
            categories={categoryChoices}
            accounts={accounts}
            dataVersion={dataVersion}
            onAdd={() => navigate("/add")}
            onOpenTransaction={setOpenTransactionId}
            onError={showError}
            onSuccess={showSuccess}
            onChanged={refreshEverything}
          />
        );

      case "/rules":
        return (
          <RulesPage
            categories={categories}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onChanged={refreshEverything}
          />
        );

      case "/accounts":
        return (
          <AccountsPage
            sources={sources}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onChanged={refreshEverything}
          />
        );

      case "/quality":
        return (
          <DataQualityPage
            source={filters.source}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onFixed={refreshEverything}
          />
        );

      case "/ask":
        return (
          <AskPage
            source={filters.source}
            onFilterChange={changeFilters}
            onError={showError}
          />
        );

      case "/forecast":
        return <ForecastPage
            source={filters.source}
            month={filters.month}
            dataVersion={dataVersion}
          />;

      case "/recurring":
        return <RecurringPage source={filters.source} dataVersion={dataVersion} />;

      case "/duplicates":
        return (
          <DuplicatesPage
            source={filters.source}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onOpenTransaction={setOpenTransactionId}
          />
        );

      case "/upload":
        return (
          <UploadPage
            sources={sources}
            onUpload={handleUpload}
            uploading={uploading}
            uploadProgress={uploadProgress}
            lastUpload={lastUpload}
            onDelete={handleDeleteUpload}
            filters={filters}
            onFilterChange={changeFilters}
          />
        );

      case "/categories":
        return (
          <CategoriesPage
            categories={categories}
            summary={summary || { by_category: [] }}
            onSelectCategory={(category) =>
              changeFilters({ ...EMPTY_FILTERS, category })
            }
            choices={categoryChoices}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onChanged={refreshEverything}
          />
        );

      case "/model":
        return (
          <ModelPage
            source={filters.source}
            dataVersion={dataVersion}
            onRetrained={refreshEverything}
            onError={showError}
          />
        );

      case "/settings":
        return (
          <SettingsPage
            session={session}
            summary={summary || {
              transaction_count: 0,
              by_category_source: [],
            }}
            sources={sources}
            categories={categories}
            onSignOut={handleSignOut}
            dataVersion={dataVersion}
            onError={showError}
            onSuccess={showSuccess}
            onChanged={refreshEverything}
          />
        );

      default:
        return (
          <DashboardPage
            summary={summary}
            trends={trends}
            transactions={page.items}
            anomalies={anomalies}
            health={health}
            scopeLabel={scopeLabel}
            onSelectCategory={selectCategory}
            onOpenTransaction={setOpenTransactionId}
          />
        );
    }
  }
}
