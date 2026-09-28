// Shared fetch helper. credentials: "include" is essential - without it,
// the browser will NOT send the HTTP-only session cookie on cross-origin
// requests (React on :5173, API on :8871), even though the cookie exists.
const API_BASE = "http://localhost:8871/api";

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = new Error(`Request failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  // DELETE / some responses may have no body
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

export const api = {
  login: (email, password) =>
    apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => apiFetch("/auth/me"),
  logout: () => apiFetch("/auth/logout", { method: "POST" }),
  listFixtures: () => apiFetch("/fixtures"),
  getFixture: (id) => apiFetch(`/fixtures/${id}`),
  createFixture: (data) => apiFetch("/fixtures", { method: "POST", body: JSON.stringify(data) }),
  updateFixture: (id, data) => apiFetch(`/fixtures/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteFixture: (id) => apiFetch(`/fixtures/${id}`, { method: "DELETE" }),
};