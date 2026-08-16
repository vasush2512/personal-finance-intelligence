/**
 * Every call to the backend lives here. No component fetches directly.
 *
 * That rule is why the whole app can be pointed at a different backend by
 * changing one line, and why an error message only has to be formatted once.
 */

/**
 * Where the API lives.
 *
 * `VITE_API_URL` is read at build time, not at run time — Vite substitutes the
 * literal into the bundle, so the hosting platform must have it set before the
 * build, not after. Unset, it falls back to the local uvicorn address, which
 * keeps `npm run dev` working with no .env file at all.
 *
 * The trailing slash is stripped because every caller below writes
 * `${BASE_URL}/api/...`, and a base ending in "/" would produce "//api/..." —
 * which some hosts answer and others 404, a difference not worth debugging.
 */
const BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

/**
 * The session token, held in module scope and mirrored to sessionStorage.
 *
 * Every request now carries it. Until recently the backend never asked who was
 * calling, so this file did not need to know — signing in was a browser-side
 * fiction. It is not any more: without this header the API answers 401.
 *
 * sessionStorage rather than localStorage: it ends with the tab, so a shared
 * machine does not stay signed in after the window closes.
 */
const TOKEN_KEY = "expense-tracker-token";

let authToken = null;
try {
  authToken = sessionStorage.getItem(TOKEN_KEY);
} catch {
  // Private browsing can refuse storage entirely. The app still works for the
  // life of the page; it just will not survive a reload.
}

export function setToken(token) {
  authToken = token || null;
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* see above */
  }
}

export function getToken() {
  return authToken;
}

/** Authorization header when signed in, nothing when not. */
function authHeaders() {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

/**
 * Turn a failed response into an Error carrying the backend's own message.
 *
 * FastAPI puts the message in `detail`, which is a string for most errors
 * but an object for a bad upload (message + detected_columns) and an array
 * for validation errors. All three have to read well in a toast.
 */
async function describeFailure(response) {
  let detail;
  try {
    const body = await response.json();
    detail = body.detail;
  } catch {
    return `Request failed (${response.status})`;
  }

  if (typeof detail === "string") return detail;

  if (detail && typeof detail === "object" && detail.message) {
    const columns = detail.detected_columns;
    if (columns && columns.length) {
      return `${detail.message} Columns found: ${columns.join(", ")}`;
    }
    return detail.message;
  }

  if (Array.isArray(detail) && detail.length && detail[0].msg) {
    return detail[0].msg;
  }

  return `Request failed (${response.status})`;
}

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    // The status travels with the message so a caller can react to the kind
    // of failure, not just print it — the sign-up form uses 409 to offer
    // "sign in instead" rather than only repeating the text.
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/** Build a query string, leaving out empty filters. */
function queryString(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.append(key, value);
    }
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Register a new account. 409 means the address is already taken. */
export async function signUp({ email, password, name }) {
  const account = await request("/api/auth/sign-up", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password, name }),
  });
  setToken(account.token);
  return account;
}

/**
 * Check an email and password.
 *
 * 401 is deliberately the same message whether the address is unknown or the
 * password is wrong, so do not try to tell the two apart here either.
 */
export async function signIn({ email, password }) {
  const account = await request("/api/auth/sign-in", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  setToken(account.token);
  return account;
}

/** There is no server session to end, so this must never block signing out. */
export async function signOut() {
  try {
    const response = await fetch(`${BASE_URL}/api/auth/sign-out`, {
      method: "POST",
      headers: authHeaders(),
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    // Cleared whatever the server said. A sign-out that leaves the token
    // behind because the network blipped is the one failure that matters.
    setToken(null);
  }
}

/**
 * Whether the stored token is still good, and who it belongs to.
 *
 * Called on load so the app asks the server rather than trusting what the
 * browser remembers about itself — a token can expire or be signed out from
 * another tab.
 */
export async function whoAmI() {
  if (!authToken) return null;
  try {
    return await request("/api/auth/me");
  } catch {
    setToken(null);
    return null;
  }
}

/**
 * Liveness check, used by the Settings page to say whether the backend is
 * actually reachable. Deliberately not routed through `request`: a failure
 * here is the answer, not an error to surface in a toast.
 */
export async function getHealth() {
  try {
    const response = await fetch(`${BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

/** Where this frontend is pointed. Shown on the Settings page. */
export const API_BASE_URL = BASE_URL;

/** The category vocabulary. Comes from the backend so it has one home. */
export function getCategories() {
  return request("/api/categories");
}

export function getTransactions(filters) {
  return request(`/api/transactions${queryString(filters)}`);
}

/**
 * One transaction with the analysis behind any flag on it.
 *
 * Separate from the list because assembling it runs a peer query over six
 * months of the category — wasted on rows nobody opened.
 */
export function getTransaction(id) {
  return request(`/api/transactions/${id}`);
}

/** The 0-100 health score and the components behind it. */
export function getFinancialHealth(params) {
  return request(`/api/financial-health${queryString(params)}`);
}

/** Pairs that may be one payment recorded twice. */
export function getDuplicates(params) {
  return request(`/api/duplicates${queryString(params)}`);
}

/**
 * Record what the user decided about a suggested duplicate pair.
 *
 * Returns 204 with no body, so this cannot go through `request`, which always
 * parses JSON.
 */
export async function setDuplicateVerdict({ firstId, secondId, isDuplicate }) {
  const response = await fetch(`${BASE_URL}/api/duplicates/verdict`, {
    method: "POST",
    headers: { ...JSON_HEADERS, ...authHeaders() },
    body: JSON.stringify({
      first_id: firstId,
      second_id: secondId,
      is_duplicate: isDuplicate,
    }),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

/** Merchants being paid on a regular rhythm. */
export function getRecurring(params) {
  return request(`/api/recurring${queryString(params)}`);
}

/** Plain-English observations drawn from figures already computed. */
export function getInsights(params) {
  return request(`/api/insights${queryString(params)}`);
}

/** Next month projected from complete months. Never a claim about the future. */
export function getForecast(params) {
  return request(`/api/forecast${queryString(params)}`);
}

/** What is labelling the data, and how sure it is. */
export function getModelStats(params) {
  return request(`/api/model/stats${queryString(params)}`);
}

/** Category corrections the user has made, newest first. */
export function getFeedback(params) {
  return request(`/api/feedback${queryString(params)}`);
}

/** One month written as paragraphs. Omit `month` for the latest. */
export function getStory(params) {
  return request(`/api/story${queryString(params)}`);
}

/**
 * Download a file from the API.
 *
 * Not routed through `request`, which parses JSON — the response here is a
 * spreadsheet. The blob is fetched rather than linked to directly so that a
 * failure surfaces as a toast like every other error, instead of navigating
 * the browser away from the app to render a JSON error page.
 *
 * The object URL is revoked immediately: keeping it alive holds the whole file
 * in memory, and a 50,000-row workbook is not small.
 */
async function download(path, fallbackName) {
  const response = await fetch(`${BASE_URL}${path}`, { headers: authHeaders() });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }

  // The server names the file; this only guesses if the header is missing.
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const name = match ? match[1] : fallbackName;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  return name;
}

/** Transactions as a file, filtered exactly as the table is. */
export function exportTransactions(params) {
  return download(
    `/api/export/transactions${queryString(params)}`,
    `transactions.${params.format || "csv"}`
  );
}

/** Category totals, monthly trends and top merchants. */
export function exportSummary(params) {
  return download(
    `/api/export/summary${queryString(params)}`,
    `summary.${params.format || "csv"}`
  );
}

/**
 * Ask a question about the transactions.
 *
 * Keyword matching on the backend, not a language model — see AskPage for the
 * full statement of that. A question it cannot place comes back with
 * understood=false rather than a guess.
 */
export function ask(question, params) {
  return request(`/api/ask${queryString(params)}`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ question }),
  });
}

// --- manually entered transactions ---------------------------------------

/** Record one transaction by hand. */
export function addManual(entry) {
  return request("/api/manual", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(entry),
  });
}

/** Edit a manual transaction. Imported rows are refused with a 404. */
export function updateManual(id, changes) {
  return request(`/api/manual/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  });
}

/** Returns 204 with no body, so it cannot go through `request`. */
export async function deleteManual(id) {
  const response = await fetch(`${BASE_URL}/api/manual/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

/** The Personal Expenses header: today, this month, average, largest. */
export function getManualSummary(params) {
  return request(`/api/manual/summary${queryString(params)}`);
}

/**
 * What the existing rules make of a merchant name.
 *
 * Offered for acceptance, never applied on its own - the form shows it and
 * the user stays in control.
 */
export function suggestCategory(merchant) {
  return request(`/api/manual/suggest${queryString({ merchant })}`);
}

export function getPaymentMethods() {
  return request("/api/manual/payment-methods");
}

// --- categories the user defined, and tags -------------------------------

/** Built-in and custom categories in one list, with usage counts. */
export function getCategoryChoices() {
  return request("/api/category-choices");
}

export function getUserCategories(params) {
  return request(`/api/user-categories${queryString(params)}`);
}

export function createUserCategory(category) {
  return request("/api/user-categories", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(category),
  });
}

export function updateUserCategory(id, changes) {
  return request(`/api/user-categories/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  });
}

/** `moveTo` is required when transactions still use the category. */
export function deleteUserCategory(id, moveTo) {
  return request(
    `/api/user-categories/${id}${queryString({ move_to: moveTo })}`,
    { method: "DELETE" }
  );
}

export function getTags() {
  return request("/api/tags");
}

export async function deleteTag(id) {
  const response = await fetch(`${BASE_URL}/api/tags/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

// --- preferences ----------------------------------------------------------

/** This user's settings, with defaults the first time they are read. */
export function getSettings() {
  return request("/api/settings");
}

/**
 * What each setting may be set to.
 *
 * Served by the backend rather than hardcoded here, so the two cannot drift —
 * the same reason the category list comes from an endpoint.
 */
export function getSettingsOptions() {
  return request("/api/settings/options");
}

export function updateSettings(changes) {
  return request("/api/settings", {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  });
}

// --- monthly budgets ------------------------------------------------------

/** Every limit the user has set. */
export function getBudgets() {
  return request("/api/budgets");
}

/** Each budget against what has been spent on it this month. */
export function getBudgetProgress(params) {
  return request(`/api/budgets/progress${queryString(params)}`);
}

/** Upsert: setting a category that already has a limit replaces it. */
export function setBudget({ category, amount }) {
  return request("/api/budgets", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ category, amount }),
  });
}

export function updateBudget(id, changes) {
  return request(`/api/budgets/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  });
}

export async function deleteBudget(id) {
  const response = await fetch(`${BASE_URL}/api/budgets/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

// --- one-click templates --------------------------------------------------

export function getQuickExpenses() {
  return request("/api/quick-expenses");
}

export function createQuickExpense(template) {
  return request("/api/quick-expenses", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(template),
  });
}

/** Record a real transaction from a template. The template stays saved. */
export function useQuickExpense(id) {
  return request(`/api/quick-expenses/${id}/use`, { method: "POST" });
}

export async function deleteQuickExpense(id) {
  const response = await fetch(`${BASE_URL}/api/quick-expenses/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

// --- the user's own categorisation rules ---------------------------------

export function getRules() {
  return request("/api/rules");
}

export function createRule({ keyword, category, priority }) {
  return request("/api/rules", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ keyword, category, priority: priority ?? 100 }),
  });
}

/** How many rows a keyword would change, before it changes them. */
export function previewRule(keyword, onlyUncategorised = true) {
  return request(
    `/api/rules/preview${queryString({
      keyword,
      only_uncategorised: onlyUncategorised,
    })}`
  );
}

export function applyRule(id, onlyUncategorised = true) {
  return request(
    `/api/rules/${id}/apply${queryString({ only_uncategorised: onlyUncategorised })}`,
    { method: "POST" }
  );
}

export function updateRule(id, changes) {
  return request(`/api/rules/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  });
}

/** Returns 204 with no body, so it cannot go through `request`. */
export async function deleteRule(id) {
  const response = await fetch(`${BASE_URL}/api/rules/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

// --- bank accounts --------------------------------------------------------

export function getAccounts() {
  return request("/api/accounts");
}

export function createAccount(account) {
  return request("/api/accounts", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(account),
  });
}

/** Move an already-imported statement to an account. */
export function assignStatement({ uploadId, accountId }) {
  return request("/api/accounts/assign", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ upload_id: uploadId, account_id: accountId }),
  });
}

export function deleteAccount(id) {
  return request(`/api/accounts/${id}`, { method: "DELETE" });
}

/** What is wrong, missing or odd about the imported rows. Reads only. */
export function getDataQuality(params) {
  return request(`/api/data-quality${queryString(params)}`);
}

/**
 * Apply the one repair that is safe to automate.
 *
 * Writes to the database, so it is only ever called from an explicit button
 * behind a confirmation — never on page load.
 */
export function fixDataQuality(issue, params) {
  return request(`/api/data-quality/fix${queryString(params)}`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ issue }),
  });
}

export function getSummary(params) {
  return request(`/api/summary${queryString(params)}`);
}

export function getTrends(params) {
  return request(`/api/trends${queryString(params)}`);
}

export function getAnomalies(params) {
  return request(`/api/anomalies${queryString(params)}`);
}

/** The files and worksheets rows actually came from. */
export function getSources() {
  return request("/api/sources");
}

export function updateCategory(id, category) {
  return request(`/api/transactions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category }),
  });
}

export function uploadStatement(file) {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser must set the multipart boundary.
  return request("/api/upload", { method: "POST", body: form });
}

export function retrainModel() {
  return request("/api/model/retrain", { method: "POST" });
}

export function deleteUpload(id) {
  return request(`/api/uploads/${id}`, { method: "DELETE" });
}
