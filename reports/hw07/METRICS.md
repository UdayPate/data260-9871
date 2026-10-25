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

## Part 2 - The agent loop

Code: `code/agent_loop.py` (`run_agent`), `code/tool_schemas.py` (JSON Schema for the three HW5 tools, used both to tell the model
about the tools and to validate every call), `code/agent_cases.py` + `code/agent_cases/verification_cases.json` (the three fixed cases,
their ground truth and the chain checker), `src/model_client.py` (new `chat()` method on the HW1 adapter; `complete()` is unchanged),
`code/measure_tool_reliability.py`. Model: qwen3:8b via Ollama, thinking off. Native tool calling; tool results go back as tool-role messages.

### Loop behaviour (all of it exercised by `test_agent_loop.py`, 58/58, plus a mutation check showing the tests can fail)
- **Hard limits:** `max_steps` (default 8) ends a run with `max_steps`; optional `max_tool_calls` / `max_total_tokens` end it with `budget_exhausted` (used by Part 3).
- **Invalid calls** (unknown tool, arguments that are not a JSON object, or arguments that break the tool's schema) are never executed.
  The model gets a tool-role message naming the specific problem plus the schema; if the retry is invalid too that is one *failed repair*, and
  after 2 failed repairs the run stops cleanly with `repair_failed`. A tool that answers `ok=false` (for example "fixture 99999999 not found")
  is **not** an invalid call: the message goes back to the model and the loop continues.
- **Logging:** every emitted call is logged (tool, inputs, valid or not, outcome) to JSONL and the run reports its total tool calls.

### Verification tasks (single message each, no follow-up prompting; temperature 0, seed 9871)

| Case | Task | Tool calls | Steps | Tokens | Chain check |
|---|---|---:|---:|---:|---|
| A | search "Lions", detail-lookup the first result | 2 | 3 | 3,163 | **FAIL**: looked up fixture 6; the first result is fixture 5 |
| B | team with the most fixtures, then a supporting example | 2 | 3 | 2,618 | pass |
| C | compare the first two "Basketball" fixtures (search + two detail lookups) | 3 | 4 | 2,997 | pass |

**The chain check only tests that the right tools were called; it cannot tell whether the final answer is true.** Checked afterwards against MySQL,
all three final answers contain a mistake: A reports the wrong fixture (6 instead of 5); B says fixture 6 is hosted by Santa Clara Strikers
(its home team is Oakland Titans; Strikers appear only as the away side); C swaps the home teams of fixtures 4 and 5 (truth: Santa Clara
Strikers and Sunnyvale Falcons; the answer says the reverse). This is exactly what Part 3's deterministic verifiers are for. The prompt was
deliberately **not** tuned to hide these, so Part 3 compares against an honest baseline.

### Error recovery (a nonexistent id; an impossible id)

| Request | What happened |
|---|---|
| `execute_tool("fixture_details", {"id": 99999999})` | `{"ok": false, "error": "fixture 99999999 not found"}` |
| `execute_tool("fixture_details", {"id": -5})` | `{"ok": false, "error": "id must be a positive integer, got -5"}` |
| agent asked for "fixture 99999999" | 1 tool call, the tool's error was returned to the model, final answer "not found ... check the ID"; no crash |
| agent asked for "fixture -5" | the model declined without calling a tool ("not a valid integer"); no crash |

### Reliability: 24 natural attempts (8 per case), qwen3:8b, temperature 0.7, seeds 9871 to 9894

"Before repair" counts first-try calls only (a retry after an invalid call is a repair attempt, not a first try). "After repair" also counts the invalid
first-try calls that the repair path later fixed.

| | Before repair | After repair |
|---|---:|---:|
| Well-formed first-try calls (56 calls) | 56/56 = 100% | 56/56 = 100% |
| Attempts with no failure of any kind | 24/24 | 24/24 |
| malformed arguments | 0 | 0 |
| unknown tool | 0 | 0 |
| text when a tool was required | 0 | 0 |
| lost multi-step chain | 0 | 0 |

Per case, clean after repair: A 8/8, B 8/8, C 8/8. Mean per attempt: 2.33 tool calls, 3.33 steps, 2,927 tokens, 4.7 s. All 24 stopped with `final_answer`.
**qwen3:8b never produced a malformed or unknown-tool call on its own**, so on the real schemas the repair path never had anything to do. Natural bad-id
prompts (`abc`, `5.5`, `0`, `-5`, "delete fixture 5") did not trigger an invalid call either: the model declined or searched instead (`explore_invalid_prompts.py`).
One of those prompts did hit the hard iteration ceiling (`max_steps` after 6 calls), a live example of that limit.

### Reliability under a deliberate fault: 12 stress attempts (4 per case)

To measure what the repair path actually rescues, the model was shown **drifted schemas** (parameters renamed: `query`->`text`, `id`->`fixture_id`,
`min_fixtures`->`min_count`) while the validator held the real ones. This is fault injection, not the model's natural error rate.

| | Before repair | After repair |
|---|---:|---:|
| Well-formed first-try calls (21 calls) | 1/21 = **4.8%** | 20/21 = **95.2%** |
| Attempts with no failure of any kind | 0/12 | 8/12 |
| malformed arguments | 12 | 1 |
| unknown tool | 0 | 0 |
| text when a tool was required | 0 | 0 |
| lost multi-step chain | 0 | 3 |

Of 20 invalid first-try calls, 19 were fixed by the one-reprompt repair. The remaining failures are not malformed calls: 3 attempts (all Case C) repaired their
calls but then stopped before looking up both fixtures (lost chain), and 1 attempt gave up after its invalid call and answered in text (counted as unrepaired
malformed arguments). Per case clean after repair: A 3/4, B 4/4, C 1/4.
Raw per-attempt data: `raw/part2_reliability_attempts.csv` / `.json` (with full traces), summary in `raw/part2_reliability_summary.json`, logs in `raw/agent_runs*.jsonl`.

### Caveats
- The reliability numbers measure tool-call well-formedness and chain completion, not answer correctness (see the note under the verification tasks).
- Natural runs used temperature 0.7 with a different seed per attempt; the three demonstration tasks used temperature 0, seed 9871.
- The repair policy is a design choice: each invalid call gets a reprompt, and a run stops after 2 failed repairs.
