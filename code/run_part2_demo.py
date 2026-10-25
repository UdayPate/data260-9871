"""
DATA-260 Homework 7 - Part 2 live demo: the three multi-step verification tasks (A, B, C), the error-recovery cases,
and a real-model demonstration of the repair path, run by the real agent loop against the real model
(qwen3:8b via Ollama) and the real MySQL database.

Each task is a single user message: no follow-up prompting. The chain checker then confirms from the tool-call
trace that the multi-step chain was really carried out.

Run from the repo root, inside the venv (each mode fits one terminal window, for screenshots):
    python code/run_part2_demo.py tasks     # tasks A, B, C
    python code/run_part2_demo.py errors    # error recovery (nonexistent id, impossible id)
    python code/run_part2_demo.py repair    # the repair path with the real model (stress: drifted schemas)
    python code/run_part2_demo.py           # everything
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_cases import check_chain, drifted_specs, ground_truth, load_cases  # noqa: E402
from agent_loop import DEFAULT_LOG_PATH, quiet_noisy_loggers, run_agent  # noqa: E402
from execute_tool import execute_tool  # noqa: E402
from model_client import ModelClient  # noqa: E402

SEED = 9871
quiet_noisy_loggers()


def fresh_model():
    return ModelClient(model="qwen3:8b", temperature=0.0, reasoning=False, seed=SEED)


def banner(text):
    print("\n" + "=" * 100 + f"\n{text}\n" + "=" * 100, flush=True)


def part_tasks(rows):
    truth = ground_truth()
    print(f"ground truth from MySQL: first 'Lions' result = fixture {truth['A_first_id']}; "
          f"team hosting the most fixtures = {truth['B_top_team']['team_name']} ({truth['B_top_team']['fixture_count']}); "
          f"first two 'Basketball' fixtures = {truth['C_ids']}")
    for case in load_cases():
        banner(f"TASK {case['id']}: {case['name']}\nuser> {case['prompt']}")
        out = run_agent(case["prompt"], model=fresh_model(), verbose=True)
        ok, note = check_chain(case["id"], out["trace"], truth)
        print(f"\nagent> {out['final_answer']}")
        print(f"\n[chain check] {'PASS' if ok else 'FAIL'}: {note}")
        rows.append((case["id"], case["min_tool_calls"], out["tool_calls_total"], out["stop_reason"], ok))


def part_errors(rows):
    banner("ERROR RECOVERY (a): what execute_tool itself says for bad input (no model involved)")
    for name, args in [("fixture_details", {"id": 99999999}), ("fixture_details", {"id": -5}), ("search_fixtures", {"query": "ab"})]:
        print(f"execute_tool({name!r}, {args}) ->\n    {execute_tool(name, args)}")

    banner("ERROR RECOVERY (b): the agent asked about a fixture that does not exist\nuser> Show me the details of fixture 99999999.")
    out = run_agent("Show me the details of fixture 99999999.", model=fresh_model(), verbose=True)
    print(f"\nagent> {out['final_answer']}")
    print(f"[recovery check] crashed: no | stop_reason={out['stop_reason']} | the tool's ok=false message was returned to the model: "
          f"{any('not found' in m['content'] for m in out['messages'] if m['role'] == 'tool')}")
    rows.append(("ERR-1", 1, out["tool_calls_total"], out["stop_reason"], out["stop_reason"] == "final_answer"))

    banner("ERROR RECOVERY (c): an impossible id (negative)\nuser> Show me the details of fixture -5.")
    out = run_agent("Show me the details of fixture -5.", model=fresh_model(), verbose=True)
    print(f"\nagent> {out['final_answer'] or '(no final answer: ' + out['stop_reason'] + ')'}")
    print(f"[recovery check] stop_reason={out['stop_reason']} | invalid calls={out['tool_calls_invalid']} "
          f"repaired={out['invalid_calls_repaired']} failed repairs={out['failed_repairs']}")
    rows.append(("ERR-2", 0, out["tool_calls_total"], out["stop_reason"], out["stop_reason"] in ("final_answer", "repair_failed")))


def part_repair(rows):
    prompt = load_cases()[0]["prompt"]
    banner("REPAIR PATH WITH THE REAL MODEL (stress: the model is shown DRIFTED tool schemas, the validator holds the real ones)\n"
           "user> " + prompt)
    out = run_agent(prompt, model=fresh_model(), verbose=True, offered_specs=drifted_specs())
    print(f"\nagent> {out['final_answer'] or '(no final answer: ' + out['stop_reason'] + ')'}")
    print(f"[repair check] stop_reason={out['stop_reason']} | invalid calls={out['tool_calls_invalid']} | "
          f"repaired={out['invalid_calls_repaired']} | failed repairs={out['failed_repairs']}")
    rows.append(("STRESS", 2, out["tool_calls_total"], out["stop_reason"],
                 out["stop_reason"] == "final_answer" and out["invalid_calls_repaired"] >= 1))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode not in ("all", "tasks", "errors", "repair"):
        sys.exit(f"usage: run_part2_demo.py [all|tasks|errors|repair], got {mode!r}")
    print("Run at", time.strftime("%Y-%m-%dT%H:%M:%S"), "| model qwen3:8b, temperature 0.0, seed", SEED, "| mode:", mode)
    rows = []
    if mode in ("all", "tasks"):
        part_tasks(rows)
    if mode in ("all", "errors"):
        part_errors(rows)
    if mode in ("all", "repair"):
        part_repair(rows)
    banner("SUMMARY")
    print(f"{'case':7s} {'needs>=':>8s} {'tool calls':>11s}  {'stop_reason':16s} ok")
    for r in rows:
        print(f"{r[0]:7s} {r[1]:>8d} {r[2]:>11d}  {r[3]:16s} {'yes' if r[4] else 'NO'}")
    print("\nfull tool-invocation log:", DEFAULT_LOG_PATH)
    sys.exit(0 if all(r[4] for r in rows) else 1)
