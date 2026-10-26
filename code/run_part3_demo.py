"""
DATA-260 Homework 7 - Part 3 live demo: Reflexion on a real failure.

Task C at temperature 0.7 fails its first attempt on its own (the agent states home teams it never looked up; it failed
in all 12 experiment items), so no fault injection is needed: the deterministic verifier rejects the answer, the model
writes ONE short reflection, the reflection is stored with its evidence, and the task is retried with the reflection in
context. A second demo shows a hard budget stopping a run (stop_reason budget_exhausted).

Run from the repo root, inside the venv:   python code/run_part3_demo.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_cases import load_cases  # noqa: E402
from agent_loop import quiet_noisy_loggers  # noqa: E402
from agent_verifiers import ground_truth_extended, oracle  # noqa: E402
from model_client import ModelClient  # noqa: E402
from reflexion import ReflectionStore, run_with_reflexion  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "reports" / "hw07" / "raw"
SEED = 9871
quiet_noisy_loggers()


def banner(text):
    print("\n" + "=" * 100 + f"\n{text}\n" + "=" * 100, flush=True)


def show(result, truth):
    for a in result["attempts"]:
        print(f"\n--- attempt {a['index']}{' (with the reflection in context)' if a['used_reflection'] else ' (the ordinary Part 2 run)'} ---")
        print(f"run stop_reason={a['run_stop_reason']} | verifier: {'PASS' if a['passed'] else 'FAIL'} "
              f"(unsupported claims: {a['unsupported_claims']}) | independent DB oracle says the answer is "
              f"{'correct' if oracle(result['case_id'], a['final_answer'], truth) else 'WRONG'}")
        print("answer:", (a["final_answer"] or "(none)").replace("\n", " | ")[:260])
        for c in a["claims"]:
            if not c["supported"]:
                print(f"   FAILED CLAIM [{c['id']}] {c['claim']}\n      -> {c['why']}")
    for n, r in enumerate(result["reflections"], start=1):
        print(f"\n>>> STORED REFLECTION {n} (source: {r['reflection_source']}, user {r['user_id']}, run {r['run_id']})\n    {r['reflection']}")
        print("    evidence stored with it:")
        print(json.dumps({k: r["evidence"][k] for k in ("failed_claims", "tool_calls", "key_observations")}, indent=2)[:1500])
    t = result["totals"]
    print(f"\n[reflexion result] stop_reason={result['stop_reason']} | retries={result['retries']} | final verifier pass={result['final_passed']} | "
          f"tool calls={t['tool_calls_total']} | tokens={t['tokens']} | latency={t['latency_ms']:.0f} ms | budgets={result['budgets']}")


print("Run at", time.strftime("%Y-%m-%dT%H:%M:%S"), "| qwen3:8b, temperature 0.7, seed", SEED, "(retries use seed + 1000 * attempt)")
truth = ground_truth_extended()
case_c = load_cases()[2]
reflect_model = ModelClient(model="qwen3:8b", temperature=0.0, reasoning=False, seed=SEED)
fresh = lambda i: ModelClient(model="qwen3:8b", temperature=0.7, reasoning=False, seed=SEED + 1000 * i)  # noqa: E731

banner(f"REFLEXION DEMO: Task C\nuser> {case_c['prompt']}")
store = ReflectionStore(RAW / "part3_demo_reflections.jsonl")
res = run_with_reflexion(case_c, fresh, truth["team_names"], reflect_model=reflect_model, store=store, verbose=True)
show(res, truth)

banner("BUDGET DEMO: the same task with a hard token budget of 500 (one model call already costs more than that)")
res2 = run_with_reflexion(case_c, fresh, truth["team_names"], reflect_model=reflect_model, store=ReflectionStore(),
                          max_total_tokens=500, verbose=True)
show(res2, truth)
sys.exit(0 if res["stop_reason"] in ("success", "human_review") and res2["stop_reason"] == "budget_exhausted" else 1)
