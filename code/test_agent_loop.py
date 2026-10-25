"""
DATA-260 Homework 7 - Part 2: deterministic tests of run_agent and the tool schemas.

No Ollama and no database: a scripted FakeModel plays the model and a fake executor plays execute_tool, so every
failure path (unknown tool, malformed arguments, schema violation, failed repairs, the iteration ceiling, budgets)
can be forced on purpose. The live model is exercised separately (run_part2_demo.py, measure_tool_reliability.py).

Run from the repo root, inside the venv:   python code/test_agent_loop.py
"""

import copy
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_loop import run_agent  # noqa: E402
from tool_schemas import TOOL_SPECS, ollama_tools, validate_call  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"   ({extra})" if extra and not cond else ""))


class FakeModel:
    """Replays scripted replies and remembers what it was shown on every turn."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, tools=None):
        self.seen.append(copy.deepcopy(messages))
        r = self.replies.pop(0)
        return {"content": r.get("content", ""), "tool_calls": r.get("calls", []),
                "invalid_tool_calls": r.get("bad", []), "usage": {"input_tokens": 100, "output_tokens": 10}, "latency_ms": 5.0}


def call(name, args, cid):
    return {"id": cid, "name": name, "args": args}


class FakeExecutor:
    def __init__(self, fail_ids=()):
        self.calls, self.fail_ids = [], set(fail_ids)

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "fixture_details" and args.get("id") in self.fail_ids:
            return json.dumps({"ok": False, "data": None, "error": f"fixture {args['id']} not found"})
        return json.dumps({"ok": True, "data": {"echo": name, "args": args}, "error": None})


def run(replies, **kw):
    ex = kw.pop("executor", None) or FakeExecutor()
    model = FakeModel(replies)
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.jsonl"
        out = run_agent("test question", model=model, executor=ex, log_path=log, **kw)
        out["_log"] = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return out, model, ex


# ---------------------------------------------------------------- schemas
print("### tool schemas")
check("the model is offered exactly the three HW5 tools", [t["function"]["name"] for t in ollama_tools()] ==
      ["search_fixtures", "fixture_details", "team_fixture_counts"])
for label, name, args, kind in [
    ("valid search", "search_fixtures", {"query": "Lions"}, None),
    ("valid search with limit", "search_fixtures", {"query": "Lions", "limit": 3}, None),
    ("valid details", "fixture_details", {"id": 5}, None),
    ("valid counts with no arguments", "team_fixture_counts", {}, None),
    ("unknown tool", "delete_fixture", {"id": 1}, "unknown_tool"),
    ("arguments are a string, not an object", "fixture_details", "id=5", "malformed_arguments"),
    ("arguments are a list", "fixture_details", [5], "malformed_arguments"),
    ("missing required argument", "fixture_details", {}, "schema_violation"),
    ("wrong type (id as text)", "fixture_details", {"id": "five"}, "schema_violation"),
    ("wrong type (float id)", "fixture_details", {"id": 5.5}, "schema_violation"),
    ("id below the minimum", "fixture_details", {"id": 0}, "schema_violation"),
    ("limit above the maximum", "search_fixtures", {"query": "Lions", "limit": 1000}, "schema_violation"),
    ("made-up extra argument", "search_fixtures", {"query": "Lions", "team": "Tigers"}, "schema_violation"),
    ("negative min_fixtures", "team_fixture_counts", {"min_fixtures": -1}, "schema_violation"),
]:
    got = validate_call(name, args)
    check(f"validate_call: {label} -> {kind or 'ok'}", (got[0] if got else None) == kind, str(got))
check("the problem text names the offending argument", "id" in validate_call("fixture_details", {"id": "five"})[1])

# ---------------------------------------------------------------- happy path
print("\n### happy path: two tool calls then a final answer")
out, model, ex = run([{"calls": [call("search_fixtures", {"query": "Lions"}, "c1")]},
                      {"calls": [call("fixture_details", {"id": 5}, "c2")]},
                      {"content": "Fixture 5 is Wolves vs Lions."}])
check("stops with final_answer after 3 model turns", out["stop_reason"] == "final_answer" and out["steps"] == 3)
check("both tools were executed in order", ex.calls == [("search_fixtures", {"query": "Lions"}), ("fixture_details", {"id": 5})])
check("total tool calls reported = 2 (0 invalid)", out["tool_calls_total"] == 2 and out["tool_calls_invalid"] == 0)
roles = [m["role"] for m in out["messages"]]
check("transcript is system, user, assistant, TOOL, assistant, TOOL, assistant",
      roles == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant"], str(roles))
tool_msgs = [m for m in out["messages"] if m["role"] == "tool"]
check("each tool-role message carries the matching tool_call_id and tool name",
      [(m["tool_call_id"], m["name"]) for m in tool_msgs] == [("c1", "search_fixtures"), ("c2", "fixture_details")])
check("the model saw the first tool result before choosing the second call",
      any(m["role"] == "tool" and m["tool_call_id"] == "c1" for m in model.seen[1]))
check("final answer is returned and tokens are summed (3 turns x 110)", out["final_answer"] == "Fixture 5 is Wolves vs Lions."
      and out["tokens"] == {"prompt": 300, "completion": 30})
logged = [r for r in out["_log"] if r["kind"] == "tool_call"]
check("every tool call is logged with its name and inputs",
      [(r["tool"], r["inputs"]) for r in logged] == [("search_fixtures", {"query": "Lions"}), ("fixture_details", {"id": 5})])
check("the log ends with a run summary that reports the total", out["_log"][-1]["kind"] == "run_summary"
      and out["_log"][-1]["tool_calls_total"] == 2)
buf = io.StringIO()
with redirect_stdout(buf):
    run_agent("q", model=FakeModel([{"calls": [call("fixture_details", {"id": 1}, "x")]}, {"content": "done"}]),
              executor=FakeExecutor(), log_path=Path(tempfile.gettempdir()) / "hw7_agent_test.jsonl", verbose=True)
check("verbose mode prints each call and 'total tool calls' at the end",
      "CALL  fixture_details" in buf.getvalue() and "total tool calls=1" in buf.getvalue())

# ---------------------------------------------------------------- tool errors do not crash the loop
print("\n### a tool that answers ok=false (nonexistent id)")
out, model, ex = run([{"calls": [call("fixture_details", {"id": 999999}, "c1")]},
                      {"content": "There is no fixture with id 999999."}], executor=FakeExecutor(fail_ids={999999}))
check("the loop continues and ends with a normal final answer", out["stop_reason"] == "final_answer")
check("the model was shown the tool's own error message",
      "fixture 999999 not found" in [m for m in model.seen[1] if m["role"] == "tool"][0]["content"])
check("a valid call that returns ok=false is NOT counted as an invalid call", out["tool_calls_invalid"] == 0)

# ---------------------------------------------------------------- repair path
print("\n### repair path")
out, model, ex = run([{"calls": [call("delete_fixture", {"id": 1}, "c1")]},
                      {"calls": [call("fixture_details", {"id": 1}, "c2")]},
                      {"content": "ok"}])
check("unknown tool: the call is NOT executed the first time", ex.calls == [("fixture_details", {"id": 1})])
repair_msg = [m for m in model.seen[1] if m["role"] == "tool"][0]["content"]
check("the model is re-prompted with a tool-role message naming the specific problem",
      "INVALID TOOL CALL (unknown_tool)" in repair_msg and "delete_fixture" in repair_msg and "search_fixtures" in repair_msg)
check("repaired on the next turn: 1 invalid, 1 rescued, 0 failed repairs, final answer",
      (out["tool_calls_invalid"], out["invalid_calls_repaired"], out["failed_repairs"], out["stop_reason"]) == (1, 1, 0, "final_answer"))
check("the trace marks the invalid call as repaired", out["trace"][0]["repaired"] is True and out["trace"][0]["failure_kind"] == "unknown_tool")

out, model, ex = run([{"calls": [], "bad": [{"id": "b1", "name": "fixture_details", "args": "{id: 5"}]},
                      {"calls": [call("fixture_details", {"id": 5}, "c2")]}, {"content": "ok"}])
check("malformed JSON arguments from the model are caught and repaired",
      out["trace"][0]["failure_kind"] == "malformed_arguments" and out["trace"][0]["repaired"] and out["stop_reason"] == "final_answer")

out, model, ex = run([{"calls": [call("fixture_details", {"id": "five"}, "c1")]},
                      {"calls": [call("fixture_details", {"id": 5}, "c2")]}, {"content": "ok"}])
sv = [m for m in model.seen[1] if m["role"] == "tool"][0]["content"]
check("schema violation: the repair message shows the schema and the offending argument",
      "schema_violation" in out["trace"][0]["failure_kind"] and "Schema for fixture_details" in sv and "'five'" in sv)

out, model, ex = run([{"calls": [call("fixture_details", {"id": 0}, "c1")]},
                      {"calls": [call("fixture_details", {"id": -3}, "c2")]},
                      {"calls": [call("fixture_details", {"id": "x"}, "c3")]},
                      {"content": "never reached"}])
check("two failed repairs -> the run stops cleanly with stop_reason repair_failed", out["stop_reason"] == "repair_failed"
      and out["failed_repairs"] == 2 and out["final_answer"] is None)
check("nothing invalid was ever executed", ex.calls == [] and out["tool_calls_invalid"] == 3 and out["invalid_calls_repaired"] == 0)

out, model, ex = run([{"calls": [call("fixture_details", {"id": 0}, "c1")]},
                      {"calls": [call("fixture_details", {"id": 7}, "c2")]},
                      {"calls": [call("nonexistent", {}, "c3")]},
                      {"calls": [call("fixture_details", {"id": 8}, "c4")]},
                      {"content": "ok"}])
check("separate bad calls that are each repaired do NOT add up to a failure",
      out["stop_reason"] == "final_answer" and out["invalid_calls_repaired"] == 2 and out["failed_repairs"] == 0)

out, model, ex = run([{"calls": [call("fixture_details", {"id": 1}, "c1"), call("fixture_details", {"id": 2}, "c2")]},
                      {"content": "two calls in one turn"}])
check("several calls in one turn each get their own tool-role reply, in order",
      [m["tool_call_id"] for m in out["messages"] if m["role"] == "tool"] == ["c1", "c2"] and len(ex.calls) == 2)

# ---------------------------------------------------------------- schema drift (the Part 2 stress experiment)
print("\n### offered schema differs from the validating schema")
drift = copy.deepcopy(TOOL_SPECS)
drift["fixture_details"]["parameters"]["properties"] = {"fixture_id": {"type": "integer"}}
drift["fixture_details"]["parameters"]["required"] = ["fixture_id"]
seen_tools = []


class SpyModel(FakeModel):
    def chat(self, messages, tools=None):
        seen_tools.append(tools)
        return super().chat(messages, tools)


with tempfile.TemporaryDirectory() as d:
    spy = SpyModel([{"calls": [call("fixture_details", {"fixture_id": 5}, "c1")]},
                    {"calls": [call("fixture_details", {"id": 5}, "c2")]}, {"content": "ok"}])
    ex = FakeExecutor()
    out = run_agent("q", model=spy, executor=ex, log_path=Path(d) / "l.jsonl", offered_specs=drift)
offered = {t["function"]["name"]: t["function"]["parameters"] for t in seen_tools[0]}
check("the model is shown the DRIFTED schema (fixture_id)", "fixture_id" in offered["fixture_details"]["properties"])
check("the call made with the drifted name is rejected against the REAL schema and never executed",
      out["trace"][0]["failure_kind"] == "schema_violation" and ex.calls == [("fixture_details", {"id": 5})])
check("the repair message shows the real schema and the model recovers with `id`",
      "Schema for fixture_details" in [m for m in spy.seen[1] if m["role"] == "tool"][0]["content"]
      and out["invalid_calls_repaired"] == 1 and out["stop_reason"] == "final_answer")

# ---------------------------------------------------------------- hard limits
print("\n### hard limits")
forever = [{"calls": [call("team_fixture_counts", {}, f"c{i}")]} for i in range(20)]
out, model, ex = run(forever, max_steps=4)
check("a model that never stops calling tools hits the iteration ceiling (max_steps)",
      out["stop_reason"] == "max_steps" and out["steps"] == 4 and len(ex.calls) == 4)
out, model, ex = run(forever, max_steps=10, max_tool_calls=2)
check("max_tool_calls budget stops the run (budget_exhausted) after exactly 2 executed calls",
      out["stop_reason"] == "budget_exhausted" and len(ex.calls) == 2)
out, model, ex = run(forever, max_steps=10, max_total_tokens=250)
check("max_total_tokens budget stops the run (budget_exhausted)", out["stop_reason"] == "budget_exhausted" and out["steps"] == 3)

# ---------------------------------------------------------------- chain checker and failure classifier
print("\n### chain checker + failure classification (synthetic traces)")
from agent_cases import classify_attempt  # noqa: E402

TRUTH = {"A_first_id": 5, "B_top_team": {"team_id": 1}, "C_ids": [3, 4]}


def rec(tool, inputs, valid=True, kind=None, repaired=False, retry=False):
    return {"tool": tool, "inputs": inputs, "valid": valid, "failure_kind": kind, "repaired": repaired, "repair_attempt": retry}


def verdict(case, trace, stop="final_answer"):
    return classify_attempt(case, {"trace": trace, "stop_reason": stop}, TRUTH)


v = verdict("A", [rec("search_fixtures", {"query": "Lions"}), rec("fixture_details", {"id": 5})])
check("A: search then details of the FIRST result -> clean", v["final_failure"] is None and v["first_try_failures"] == [])
v = verdict("A", [rec("search_fixtures", {"query": "Lions"})])
check("A: searched but never looked up a detail -> lost_multistep_chain", v["final_failure"] == "lost_multistep_chain")
v = verdict("A", [rec("search_fixtures", {"query": "Lions"}), rec("fixture_details", {"id": 99})])
check("A: details of the WRONG id -> lost_multistep_chain", v["final_failure"] == "lost_multistep_chain")
v = verdict("A", [])
check("no tool call at all, plain-text answer -> text_when_tool_required",
      v["final_failure"] == "text_when_tool_required" and "text_when_tool_required" in v["first_try_failures"])
v = verdict("A", [rec("search_fixtures", {"query": "Lions"}), rec("fixture_details", {"id": "5"}, False, "schema_violation", repaired=True),
                  rec("fixture_details", {"id": 5}, retry=True)])
check("a schema violation that the repair fixed: failure BEFORE repair, none AFTER",
      v["first_try_failures"] == ["malformed_arguments"] and v["final_failure"] is None and v["first_try_invalid_rescued"] == 1)
v = verdict("A", [rec("run_sql", {}, False, "unknown_tool")], stop="repair_failed")
check("an unknown tool that was never repaired -> final failure unknown_tool", v["final_failure"] == "unknown_tool")
v = verdict("A", [rec("fixture_details", {"id": 5}, False, "malformed_arguments")], stop="repair_failed")
check("unrepaired malformed arguments -> final failure malformed_arguments", v["final_failure"] == "malformed_arguments")
v = verdict("B", [rec("team_fixture_counts", {}), rec("search_fixtures", {"query": "Lions"})])
check("B: counts then a supporting example -> clean", v["final_failure"] is None)
v = verdict("B", [rec("team_fixture_counts", {})])
check("B: counts but no supporting example -> lost_multistep_chain", v["final_failure"] == "lost_multistep_chain")
v = verdict("B", [rec("search_fixtures", {"query": "Lions"})])
check("B: never asked for the counts -> lost_multistep_chain", v["final_failure"] == "lost_multistep_chain")
v = verdict("C", [rec("search_fixtures", {"query": "Basketball"}), rec("fixture_details", {"id": 3}), rec("fixture_details", {"id": 4})])
check("C: search plus BOTH detail lookups -> clean", v["final_failure"] is None)
v = verdict("C", [rec("search_fixtures", {"query": "Basketball"}), rec("fixture_details", {"id": 3})])
check("C: only one of the two detail lookups -> lost_multistep_chain", v["final_failure"] == "lost_multistep_chain")
v = verdict("C", [rec("search_fixtures", {"query": "Basketball"}), rec("fixture_details", {"id": 3})], stop="max_steps")
check("hitting the iteration ceiling mid-chain counts as a lost chain", v["final_failure"] == "lost_multistep_chain")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
for n in failed:
    print("FAILED:", n)
sys.exit(1 if failed else 0)
