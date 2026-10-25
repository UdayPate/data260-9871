"""
DATA-260 Homework 7 - Parts 2-3: the three fixed verification cases, their ground truth, and the chain checker.

Ground truth is recomputed from the live database through the same HW5 tools the agent uses, so it can never go
stale. check_chain() decides, from the agent's tool-call trace alone, whether the multi-step chain the case needs was
carried out; classify_attempt() turns a finished run into the failure categories the assignment asks for:

    malformed_arguments        a call whose arguments were not a JSON object, or broke the tool's schema
    unknown_tool               a call to a tool that does not exist
    text_when_tool_required    the model answered in plain text without calling any tool
    lost_multistep_chain       some tools were called, but the chain the task needs was not completed
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tool_schemas import TOOL_SPECS  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "agent_cases" / "verification_cases.json"

MALFORMED, UNKNOWN, TEXT, LOST = "malformed_arguments", "unknown_tool", "text_when_tool_required", "lost_multistep_chain"


def drifted_specs():
    """Stress only: rename every parameter in the schemas the MODEL sees (query->text, id->fixture_id, min_fixtures->min_count)."""
    renames = {"search_fixtures": ("query", "text"), "fixture_details": ("id", "fixture_id"),
               "team_fixture_counts": ("min_fixtures", "min_count")}
    drifted = copy.deepcopy(TOOL_SPECS)
    for tool, (old, new) in renames.items():
        params = drifted[tool]["parameters"]
        params["properties"] = {(new if k == old else k): v for k, v in params["properties"].items()}
        params["required"] = [new if k == old else k for k in params["required"]]
    return drifted


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def ground_truth(executor=None) -> dict:
    """The facts the three cases hinge on, read live from MySQL via the HW5 tools."""
    if executor is None:
        from agent_loop import quiet_noisy_loggers
        from execute_tool import execute_tool

        quiet_noisy_loggers()
        executor = execute_tool
    ask = lambda name, args: json.loads(executor(name, args))["data"]
    lions = ask("search_fixtures", {"query": "Lions"})
    basketball = ask("search_fixtures", {"query": "Basketball"})
    counts = ask("team_fixture_counts", {})
    top = sorted(counts, key=lambda t: (-t["fixture_count"], t["team_id"]))[0]
    return {
        "A_first_id": lions[0]["id"], "A_first": lions[0],
        "B_top_team": top,
        "C_ids": [f["id"] for f in basketball[:2]], "C_fixtures": basketball[:2],
    }


def _valid(trace):
    return [t for t in trace if t["valid"]]


def check_chain(case_id: str, trace: list[dict], truth: dict) -> tuple[bool, str]:
    """Was the multi-step chain this case needs actually carried out (from the valid, executed calls)?"""
    calls = _valid(trace)
    names = [t["tool"] for t in calls]
    if case_id == "A":
        for i, t in enumerate(calls):
            if t["tool"] == "search_fixtures" and "lions" in str(t["inputs"].get("query", "")).lower():
                if any(u["tool"] == "fixture_details" and u["inputs"].get("id") == truth["A_first_id"] for u in calls[i + 1:]):
                    return True, "searched 'Lions', then looked up the first result"
                return False, f"searched but never called fixture_details on the first result (id {truth['A_first_id']})"
        return False, "never searched for 'Lions'"
    if case_id == "B":
        if "team_fixture_counts" not in names:
            return False, "never asked for the per-team counts"
        after = names[names.index("team_fixture_counts") + 1:]
        if any(n in ("search_fixtures", "fixture_details") for n in after):
            return True, "got the counts, then looked for a supporting example"
        return False, "got the counts but never looked for a supporting example"
    if case_id == "C":
        search = next((i for i, t in enumerate(calls) if t["tool"] == "search_fixtures"
                       and "basketball" in str(t["inputs"].get("query", "")).lower()), None)
        if search is None:
            return False, "never searched for 'Basketball'"
        looked = {u["inputs"].get("id") for u in calls[search + 1:] if u["tool"] == "fixture_details"}
        missing = [i for i in truth["C_ids"] if i not in looked]
        return (not missing), ("looked up both fixtures" if not missing else f"never looked up fixture id(s) {missing}")
    raise ValueError(f"unknown case {case_id!r}")


def classify_attempt(case_id: str, result: dict, truth: dict) -> dict:
    """Failure categories for one finished run. `first_try_failures` are what went wrong BEFORE the repair path
    helped; `final_failure` is what is still wrong AFTER it (None = the chain was completed cleanly)."""
    trace = result["trace"]
    kind_map = {"unknown_tool": UNKNOWN, "malformed_arguments": MALFORMED, "schema_violation": MALFORMED}
    first_try = [t for t in trace if not t["repair_attempt"]]
    first_try_invalid = [t for t in first_try if not t["valid"]]
    first_try_failures = sorted({kind_map[t["failure_kind"]] for t in first_try_invalid})
    unrepaired = [t for t in first_try_invalid if not t["repaired"]]
    chain_ok, chain_note = check_chain(case_id, trace, truth)
    emitted_any = bool(trace)

    final_failure = None
    if result["stop_reason"] == "repair_failed" or unrepaired:
        final_failure = kind_map[(unrepaired or first_try_invalid)[0]["failure_kind"]]
    elif not emitted_any and result["stop_reason"] == "final_answer":
        final_failure = TEXT
    elif not chain_ok:
        final_failure = LOST
    if not emitted_any and result["stop_reason"] == "final_answer" and TEXT not in first_try_failures:
        first_try_failures = sorted(set(first_try_failures) | {TEXT})
    elif emitted_any and not chain_ok and not first_try_failures:
        first_try_failures = [LOST]
    return {"first_try_failures": first_try_failures, "final_failure": final_failure,
            "chain_complete": chain_ok, "chain_note": chain_note,
            "first_try_calls": len(first_try), "first_try_invalid": len(first_try_invalid),
            "first_try_invalid_rescued": sum(1 for t in first_try_invalid if t["repaired"])}
