// Axios instance shared by the Redux thunks (HW5 Part 1.III).
//
// HW7: authentication is a JWT bearer token, not the HW4 session cookie. The token
// returned by POST /auth/login is kept in sessionStorage (it disappears when the tab
// closes) and a request interceptor adds `Authorization: Bearer <token>` to every call.
// withCredentials is gone: no cookie is involved any more. If the server answers 401
// (expired or invalid token) the token is dropped and an "auth:expired" event tells
// App to show the login screen again.
import axios from "axios";

export const API_BASE = "http://localhost:8871/api";

const TOKEN_KEY = "hw7_access_token";
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export const http = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && tokenStore.get()) {
      tokenStore.clear();
      window.dispatchEvent(new Event("auth:expired"));
    }
    return Promise.reject(error);
  },
);

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
  login: (username, password) =>
    http.post("/auth/login", { username, password }).then((r) => {
      tokenStore.set(r.data.access_token);
      return r.data.user; // { id, username, name, email, role }
    }),
  me: () => http.get("/auth/me").then((r) => r.data),
  // A JWT is stateless, so logging out just forgets the token on this side.
  logout: () => {
    tokenStore.clear();
    return Promise.resolve();
  },
};
