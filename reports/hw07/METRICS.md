# HW7 Metrics (SID4 9871, seed 9871)

Model: `qwen3:8b` via Ollama (used from Part 2 on). Everything below comes from real runs in `RUN_LOG.txt`.

## Part 1 - JWT authentication, role-based authorization, linting

### What changed
- `users` table (MySQL `s9871_rel`) migrated by `code/web_application/migrate_hw07.py`: added `username` (unique) and
  `role` ENUM(reader, writer, moderator). The HW4 admin became `league_admin` (moderator); demo users
  `reader_user`, `writer_user`, `moderator_user` are created at startup. Passwords are bcrypt hashes (`$2b$12$...`, 60 chars).
- `code/web_application/auth_jwt.py`: `POST /auth/login`, `GET /auth/me` (also served under `/api/auth/*` for the React client),
  HS256 tokens valid 30 minutes, `get_current_user` (401) and `require_roles(...)` (403). The HW4 session code is gone from
  `api_v2.py`; it survives only at the `hw4` tag.
- React client sends `Authorization: Bearer <token>` (token kept in `sessionStorage`), shows Add/Edit only to writer/moderator and
  Delete only to moderator, and falls back to the login screen on a 401.

### Role matrix on the domain routes (HTTP status actually returned)

| Caller | List / read | Create | Update | Delete |
|---|---:|---:|---:|---:|
| no token | 401 | 401 | 401* | 401 |
| reader | 200 | **403** | **403** | **403** |
| writer | 200 | **201** | **200** | **403** |
| moderator | 200 | **201** | 200 | **200** |

\* the `PUT` with no token goes through the same `get_current_user` dependency as the other 401 cells but was not requested separately.
The same rules are applied to `/api/teams` and `/api/fixtures`; teams were checked for create (reader 403, writer 201) and delete
(writer 403, moderator 200). Delete returns 200 with a body in this API (the assignment accepts 200 or 204).

### Authentication cases (all verified, 401 unless noted)

| Case | Result |
|---|---|
| valid login (reader / writer / moderator) | 200 + JWT |
| wrong password; unknown username | 401, identical message ("Invalid username or password") - no user enumeration |
| missing field; old HW4 `email` body; 200-byte password | 422; 422; 401 (no crash) |
| `/auth/me` with no token | 401 + `WWW-Authenticate: Bearer` |
| invalid string; tampered signature; signed with another secret; `alg: none`; user id that does not exist; no `exp` | 401 "Invalid token" |
| expired token | 401 "Token expired" |
| non-Bearer header; the old HW4 session cookie | 401 |
| role demoted in MySQL, same (still valid) token used again | 403: the role is read from MySQL on every request, not trusted from the token |

### Test summary

| Script | Checks | Result |
|---|---:|---|
| `test_jwt_auth.py` (real HTTP + MySQL checked directly, cleans up its data) | 50 | 50/50 |
| `test_jwt_ui.py` (Playwright: role-aware UI, wrong password, expired/garbage token) | 29 | 29/29 |
| `test_redux_ui.py` (the HW5 browser flow, unchanged apart from logging in by username) | 22 | 22/22 |
| Postman collection run with Newman | 22 assertions / 15 requests | 0 failed |

Bugs found by running it: after removing the session code from `api_v2.py` the server failed to start because I had also
removed the `Request` import that the N+1 endpoints still use (fixed); the first version of the API test assumed `/api/fixtures`
was paginated like `/api/teams` (it returns a plain list; test fixed).

### Linting (Ruff + pre-commit)
- Config: `pyproject.toml` (rules `F`, `E4`, `E9`, `E711`, `E712`, `E722`; `E402` ignored because several scripts call `sys.path.insert`
  before importing) and `.pre-commit-config.yaml` (Ruff `v0.17.2`, no `--fix`, so the hook reports and blocks).
- Chosen deliberately narrow: the whole repo has only 15 real-bug findings under these rules (13 unused imports, 2 f-strings without
  placeholders) versus about 200 if style rules were switched on. The hook lints only staged files, so legacy files are checked when touched.
- Hook flow tested end-to-end in a throwaway repo first: 4 errors reported, `git commit` blocked (exit 1, no commit created), after
  fixing the hook prints `Passed` and the commit succeeds (exit 0).

### Caveats
- `verify_hw04.py` and `code/web_application/measure_n1.py` log in with the HW4 session cookie, so they no longer work against the HW7 server
  (they work at the `hw4` tag, which is where that scheme now lives).
- The older server-rendered HTML pages in `auth.py` (HW2-era `/login`, `/dashboard`) use their own form session and are not part of the
  graded API routes; they were left alone.
- JWTs are stateless, so "log out" only discards the token on the client; a stolen token stays valid until it expires (30 minutes).
