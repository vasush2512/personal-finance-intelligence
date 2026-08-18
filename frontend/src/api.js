const BASE_URL = (import.meta.env.VITE_API_URL || "https://personal-finance-intelligence.onrender.com").replace(/\/+$/, "");

const TOKEN_KEY = "expense-tracker-token";

let authToken = null;
try {
  authToken = sessionStorage.getItem(TOKEN_KEY);
} catch {
  // Private browsing can refuse storage entirely.
}

export function setToken(token) {
  authToken = token || null;
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Keep the in-memory token for this page lifetime. */
  }
}

export function getToken() {
  return authToken;
}

function authHeaders() {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

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
    error.status = response.status;
    throw error;
  }
  return response.json();
}

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

export async function signUp({ email, password, name }) {
  const account = await request("/api/auth/sign-up", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password, name }),
  });
  setToken(account.token);
  return account;
}

export async function signIn({ email, password }) {
  const account = await request("/api/auth/sign-in", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  setToken(account.token);
  return account;
}

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
    setToken(null);
  }
}

export async function whoAmI() {
  if (!authToken) return null;
  try {
    return await request("/api/auth/me");
  } catch {
    setToken(null);
    return null;
  }
}

export async function getHealth() {
  try {
    const response = await fetch(`${BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export const API_BASE_URL = BASE_URL;

export function getCategories() { return request("/api/categories"); }
export function getTransactions(filters) { return request(`/api/transactions${queryString(filters)}`); }
export function getTransaction(id) { return request(`/api/transactions/${id}`); }
export function getFinancialHealth(params) { return request(`/api/financial-health${queryString(params)}`); }
export function getDuplicates(params) { return request(`/api/duplicates${queryString(params)}`); }

export async function setDuplicateVerdict({ firstId, secondId, isDuplicate }) {
  const response = await fetch(`${BASE_URL}/api/duplicates/verdict`, {
    method: "POST",
    headers: { ...JSON_HEADERS, ...authHeaders() },
    body: JSON.stringify({ first_id: firstId, second_id: secondId, is_duplicate: isDuplicate }),
  });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

export function getRecurring(params) { return request(`/api/recurring${queryString(params)}`); }
export function getInsights(params) { return request(`/api/insights${queryString(params)}`); }
export function getForecast(params) { return request(`/api/forecast${queryString(params)}`); }
export function getModelStats(params) { return request(`/api/model/stats${queryString(params)}`); }
export function getFeedback(params) { return request(`/api/feedback${queryString(params)}`); }
export function getStory(params) { return request(`/api/story${queryString(params)}`); }

async function download(path, fallbackName) {
  const response = await fetch(`${BASE_URL}${path}`, { headers: authHeaders() });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }

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

export function exportTransactions(params) { return download(`/api/export/transactions${queryString(params)}`, `transactions.${params.format || "csv"}`); }
export function exportSummary(params) { return download(`/api/export/summary${queryString(params)}`, `summary.${params.format || "csv"}`); }

export function ask(question, params) {
  return request(`/api/ask${queryString(params)}`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ question }),
  });
}

export function addManual(entry) { return request("/api/manual", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(entry) }); }
export function updateManual(id, changes) { return request(`/api/manual/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(changes) }); }

export async function deleteManual(id) {
  const response = await fetch(`${BASE_URL}/api/manual/${id}`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

export function getManualSummary(params) { return request(`/api/manual/summary${queryString(params)}`); }
export function suggestCategory(merchant) { return request(`/api/manual/suggest${queryString({ merchant })}`); }
export function getPaymentMethods() { return request("/api/manual/payment-methods"); }
export function getCategoryChoices() { return request("/api/category-choices"); }
export function getUserCategories(params) { return request(`/api/user-categories${queryString(params)}`); }
export function createUserCategory(category) { return request("/api/user-categories", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(category) }); }
export function updateUserCategory(id, changes) { return request(`/api/user-categories/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(changes) }); }
export function deleteUserCategory(id, moveTo) { return request(`/api/user-categories/${id}${queryString({ move_to: moveTo })}`, { method: "DELETE" }); }
export function getTags() { return request("/api/tags"); }

export async function deleteTag(id) {
  const response = await fetch(`${BASE_URL}/api/tags/${id}`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

export function getSettings() { return request("/api/settings"); }
export function getSettingsOptions() { return request("/api/settings/options"); }
export function updateSettings(changes) { return request("/api/settings", { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(changes) }); }
export function getBudgets() { return request("/api/budgets"); }
export function getBudgetProgress(params) { return request(`/api/budgets/progress${queryString(params)}`); }
export function setBudget({ category, amount }) { return request("/api/budgets", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ category, amount }) }); }
export function updateBudget(id, changes) { return request(`/api/budgets/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(changes) }); }
export function deleteBudget(id) { return request(`/api/budgets/${id}`, { method: "DELETE" }); }
export function getAccounts() { return request("/api/accounts"); }
export function createAccount(account) { return request("/api/accounts", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(account) }); }
export function updateAccount(id, changes) { return request(`/api/accounts/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(changes) }); }

export async function deleteAccount(id) {
  const response = await fetch(`${BASE_URL}/api/accounts/${id}`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) {
    const error = new Error(await describeFailure(response));
    error.status = response.status;
    throw error;
  }
  return true;
}

export async function uploadStatement(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  const result = await new Promise((resolve, reject) => {
    xhr.open("POST", `${BASE_URL}/api/upload`);
    Object.entries(authHeaders()).forEach(([key, value]) => xhr.setRequestHeader(key, value));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch { reject(new Error("Upload succeeded but the server returned invalid JSON.")); }
        return;
      }
      let message = `Request failed (${xhr.status})`;
      try {
        const body = JSON.parse(xhr.responseText);
        if (typeof body.detail === "string") message = body.detail;
        else if (body.detail?.message) message = body.detail.message;
      } catch {}
      const error = new Error(message);
      error.status = xhr.status;
      reject(error);
    };
    xhr.onerror = () => reject(new Error("Could not reach the backend."));
    xhr.send(form);
  });
  return result;
}

export function deleteUpload(uploadId) { return request(`/api/uploads/${uploadId}`, { method: "DELETE" }); }
export function getSources() { return request("/api/sources"); }
export function getSummary(params) { return request(`/api/summary${queryString(params)}`); }
export function getTrends(params) { return request(`/api/trends${queryString(params)}`); }
export function getAnomalies(params) { return request(`/api/anomalies${queryString(params)}`); }
