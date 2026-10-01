// Axios instance shared by the Redux thunks (HW5 Part 1.III).
//
// withCredentials: true is essential - without it the browser will NOT send
// the HTTP-only session cookie on cross-origin requests (React on :5173,
// API on :8871), even though the cookie exists. The cookie is also marked
// Secure, which a browser accepts over http://localhost because localhost
// counts as a trustworthy origin; a non-browser HTTP client would not
// resend it and would need the cookie passed explicitly per request.
import axios from "axios";

export const API_BASE = "http://localhost:8871/api";

export const http = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

/**
 * Turns an axios error into a short string a reducer can store and a screen
 * can render. FastAPI returns `detail` as a plain string for the 404/409
 * HTTPExceptions raised in api_v2.py, but as an ARRAY of objects for
 * Pydantic 422 validation errors - both shapes have to be handled or the UI
 * ends up rendering "[object Object]".
 */
export function errorMessage(err) {
  const detail = err?.response?.data?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "request";
        return `${field}: ${d.msg}`;
      })
      .join("; ");
  }

  if (err?.response?.status) return `Request failed (HTTP ${err.response.status})`;
  return err?.message || "Network error";
}

// Auth stays outside Redux: it is not the primary domain entity, and the
// assignment asks for a slice for the domain entity specifically.
export const api = {
  login: (email, password) =>
    http.post("/auth/login", { email, password }).then((r) => r.data),
  me: () => http.get("/auth/me").then((r) => r.data),
  logout: () => http.post("/auth/logout").then((r) => r.data),
};
