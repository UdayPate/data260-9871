"""
DATA-260 Homework 5 - Part 4: the one safe entry point the Part 5 agent
calls to run any of the three domain tools.

execute_tool(name, inputs) dispatches to the matching function in
domain_server.py, wraps the call in Part 3's retry/timeout policy (these
are exactly the "storage operations that may fail" that policy targets),
and always returns a JSON STRING in the {ok, data, error} shape from
Part 2B/3 - never raises, regardless of what goes wrong (unknown tool
name, bad input, a DB error, a timeout).

Part 5.I safety rule: search_fixtures with a query under 3 characters is
rejected here, before the domain tool or any retry/DB call ever runs - a
1-2 character query would match a huge fraction of the 5001 fixtures and
isn't a meaningful search. Violating it returns the normal {ok: false, ...}
envelope, never an exception.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from domain_server import fixture_details, search_fixtures, team_fixture_counts
from retry_policy import call_with_retry

TOOLS = {
    "search_fixtures": search_fixtures,
    "fixture_details": fixture_details,
    "team_fixture_counts": team_fixture_counts,
}


def execute_tool(name: str, inputs: dict, tools: dict | None = None) -> str:
    """Run one domain tool by name. Always returns a JSON string shaped
    {"ok": bool, "data": ..., "error": str | None} - never raises.

    `tools` is a dependency-injection point: the Part 4 test runner passes
    in fake tool callables so tests run offline, without a live MySQL
    connection. Real callers omit it and get the real domain tools.
    """
    registry = tools or TOOLS
    fn = registry.get(name)
    if fn is None:
        return json.dumps({
            "ok": False,
            "data": None,
            "error": f"unknown tool: {name!r} (known: {sorted(registry)})",
        })

    # Part 5.I safety rule (domain-specific, lives here per the assignment,
    # not inside the domain tool itself).
    if name == "search_fixtures":
        query = (inputs.get("query") or "").strip()
        if 0 < len(query) < 3:
            return json.dumps({
                "ok": False,
                "data": None,
                "error": "query too broad: must be at least 3 characters",
            })

    def call():
        # The domain tools already return the {ok, data, error} envelope
        # themselves for a REJECTED input (e.g. empty query). Only a crash
        # inside them (a bad kwarg, a DB outage) should trigger a retry.
        return fn(**inputs)

    outcome = call_with_retry(call, max_retries=2, base_delay_s=0.05, timeout_s=5.0)

    if outcome["ok"]:
        # outcome["data"] IS the tool's own {ok, data, error} envelope.
        envelope = outcome["data"]
    else:
        # The tool itself crashed (bad kwargs, DB error, timeout) even
        # after retries - build the envelope here instead.
        envelope = {"ok": False, "data": None, "error": outcome["error"]}

    return json.dumps(envelope)
