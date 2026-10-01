# HW5 METRICS

## Part 3.18 - Tool contracts under stress

Same three domain tools and rejected calls captured in Part 2B
(`reports/hw05/screenshots/*_invalid.png`). Schemas pulled directly from the
running server via `list_tools()`.

| Tool | Expected input schema | Rejected input | Returned error | Why rejected |
|---|---|---|---|---|
| `search_fixtures` | `{query: string (required), limit: integer = 10}` | `{"query": ""}` | `{"ok": false, "data": null, "error": "query must not be empty"}` | Empty string fails the non-empty check before any DB call. |
| `fixture_details` | `{id: integer (required)}` | `{"id": 999999}` | `{"ok": false, "data": null, "error": "fixture 999999 not found"}` | Well-formed input, but no row with that id exists. |
| `team_fixture_counts` | `{min_fixtures: integer = 0}` | `{"min_fixtures": -2}` | `{"ok": false, "data": null, "error": "min_fixtures must be >= 0, got -2"}` | Negative threshold is meaningless for a count filter. |

All three return the envelope as a normal successful MCP result (not an
MCP-level error) - `ok: false` carries the rejection, matching what Part 4's
`execute_tool` and Part 5's safety rule both reuse.

## Part 3.19 - retry policy demo scenarios

`code/measure_retry_policy.py`, run 2026-10-01 (real output in RUN_LOG.txt):

| Scenario | Result |
|---|---|
| Success on first attempt | `ok: true`, 1 attempt |
| Failure then success on retry | `ok: true`, 2 attempts |
| Failure after all allowed retries | `ok: false`, 4 attempts, clean error (no crash) |

## Part 3.20 - VERIFY_SEED fault injection (150 calls, 50 per rate)

VERIFY_SEED = 269871. Raw per-call data: `reports/hw05/raw/part3_fault_injection_calls.json`.
Summary: `reports/hw05/raw/part3_fault_injection_summary.json`.

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |
|---|---|---|---|
| 0%  | 100% | 13.1 | 31.0 |
| 20% | 100% | 28.4 | 187.0 |
| 50% | 94%  | 80.0 | 428.4 |

**What this shows:** with max_retries=3 (4 attempts total), the retry policy
fully absorbs 0% and 20% injected failure - every call still succeeds,
because the chance of failing 4 attempts in a row at 20% is only 0.2^4 ~
0.16%. At 50%, failing all 4 attempts has probability 0.5^4 = 6.25%, which
matches the observed 6% failure rate almost exactly. The cost is latency:
mean latency roughly doubles from 0% to 20% and climbs further at 50%,
and p99 grows much faster than the mean, because p99 is dominated by the
few calls that need several retries with exponential backoff before they
either succeed or exhaust all attempts.

**Is this policy suitable for an interactive assistant?** Reasonably, up to
about 20% failure - every call still succeeds and the latency stays under
~200ms even at p99. At 50%, a p99 of 428ms starts to feel sluggish for an
interactive turn, and a 6% outright failure rate means roughly 1 in 17
requests still comes back as an error the user has to see.

**For batch processing** (longer processing times acceptable): increase
max_retries (e.g. 5-6) and raise max_delay_s (e.g. 5-10s instead of 1s), so
a transient outage gets more chances to clear instead of giving up quickly.
timeout_s could also grow, since batch jobs aren't blocking a user waiting
on a response. The tradeoff is the same one visible in the p99 numbers
above: more retries and longer backoff trade worse worst-case latency for a
higher overall success rate, which is the right trade for a batch job and
the wrong one for an interactive one.
