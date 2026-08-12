/**
 * Every call to the backend lives here. No component fetches directly.
 *
 * That rule is why the whole app can be pointed at a different backend by
 * changing one line, and why an error message only has to be formatted once.
 */

const BASE_URL = "http://127.0.0.1:8000";

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

async function request(path, options) {
  const response = await fetch(`${BASE_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(await describeFailure(response));
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

/** The category vocabulary. Comes from the backend so it has one home. */
export function getCategories() {
  return request("/api/categories");
}

export function getTransactions(filters) {
  return request(`/api/transactions${queryString(filters)}`);
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
