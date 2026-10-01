"""
DATA-260 Homework 5 - Part 4.23/24: offline test runner for execute_tool.

Runs completely offline: fake tool callables are injected in place of the
real domain tools (see execute_tool's `tools` parameter), so there is no
MySQL connection, no LLM, and the tests are fully repeatable. Each fake
mirrors the real tool's validation exactly (same error messages), matching
the cases documented in Part 3.

Run from code/, inside the venv:
    python test_execute_tool.py
"""

import json
import sys

from execute_tool import execute_tool

# ---------------------------------------------------------------------
# Fake tools (dependency injection) - no MySQL, no network, deterministic.
# ---------------------------------------------------------------------

def fake_search_fixtures(query: str, limit: int = 10):
    if not query or not query.strip():
        return {"ok": False, "data": None, "error": "query must not be empty"}
    return {"ok": True, "data": [{"id": 1, "fixture_name": f"Fake match for {query!r}"}], "error": None}


def fake_fixture_details(id: int):
    if id == 999999:
        return {"ok": False, "data": None, "error": f"fixture {id} not found"}
    return {"ok": True, "data": {"id": id, "fixture_name": "Fake Fixture"}, "error": None}


def fake_team_fixture_counts(min_fixtures: int = 0):
    if min_fixtures < 0:
        return {"ok": False, "data": None, "error": f"min_fixtures must be >= 0, got {min_fixtures}"}
    return {"ok": True, "data": [{"team_id": 1, "fixture_count": 5}], "error": None}


FAKE_TOOLS = {
    "search_fixtures": fake_search_fixtures,
    "fixture_details": fake_fixture_details,
    "team_fixture_counts": fake_team_fixture_counts,
}

# ---------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------

PASS = FAIL = 0


def check(label: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}   {extra}")


def run(name, inputs):
    return json.loads(execute_tool(name, inputs, tools=FAKE_TOOLS))


# 1-2: search_fixtures
r = run("search_fixtures", {"query": "Lions", "limit": 5})
check("search_fixtures: valid input -> ok=true", r["ok"] is True and r["data"], r)

r = run("search_fixtures", {"query": ""})
check(
    "search_fixtures: invalid (empty query) -> ok=false, documented error",
    r["ok"] is False and r["error"] == "query must not be empty",
    r,
)

# 3-4: fixture_details
r = run("fixture_details", {"id": 4})
check("fixture_details: valid input -> ok=true", r["ok"] is True and r["data"]["id"] == 4, r)

r = run("fixture_details", {"id": 999999})
check(
    "fixture_details: invalid (unknown id) -> ok=false, documented error",
    r["ok"] is False and r["error"] == "fixture 999999 not found",
    r,
)

# 5-6: team_fixture_counts
r = run("team_fixture_counts", {"min_fixtures": 100})
check("team_fixture_counts: valid input -> ok=true", r["ok"] is True and isinstance(r["data"], list), r)

r = run("team_fixture_counts", {"min_fixtures": -2})
check(
    "team_fixture_counts: invalid (negative min_fixtures) -> ok=false, documented error",
    r["ok"] is False and r["error"] == "min_fixtures must be >= 0, got -2",
    r,
)

# 7: execute_tool's own dispatch - an unknown tool name must not crash it.
r = run("delete_everything", {})
check("execute_tool: unknown tool name -> ok=false, no crash", r["ok"] is False and "unknown tool" in r["error"], r)

# 8: Part 5.I safety rule - a query under 3 chars is blocked before the
# tool (real or fake) ever runs, without raising.
r = run("search_fixtures", {"query": "a"})
check(
    "execute_tool: safety rule blocks a too-broad query, no crash",
    r["ok"] is False and r["error"] == "query too broad: must be at least 3 characters",
    r,
)

# 9: Part 5.III - run_agent with MockModel must stop at max_steps. Offline:
# MockModel never calls a live model, FAKE_TOOLS never touches MySQL, and
# the log is written to a throwaway temp file, not the real agent_runs.jsonl.
import tempfile
from pathlib import Path

from agent import MockModel, run_agent

with tempfile.TemporaryDirectory() as tmp:
    result = run_agent(
        "irrelevant - MockModel ignores the input",
        model=MockModel(),
        max_steps=3,
        tools=FAKE_TOOLS,
        log_path=Path(tmp) / "test_agent_runs.jsonl",
    )
check(
    "run_agent + MockModel: stops at max_steps, offline",
    result["stop_reason"] == "max_steps_ceiling" and result["steps"] == 3,
    result,
)

print(f"\n{PASS}/{PASS + FAIL} tests passed")
sys.exit(0 if FAIL == 0 else 1)
