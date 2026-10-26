"""
DATA-260 Homework 7 - Part 3: paired comparison, original agent loop vs the same loop with bounded Reflexion.

For every (case, item) the ORIGINAL run is attempt 0 (the Part 2 loop, temperature 0.7, seed 9871+item). Reflexion is then
applied to that very same run (first_run=...), so the two arms share attempt 0 and differ only in whether failures are
followed by reflect-and-retry. Both arms are judged by the deterministic verifier AND by the database oracle, and every
disagreement between the two judges is recorded (false rejection / false acceptance).

Run from the repo root, inside the venv:
    python code/measure_reflexion.py --items 12            # full run
    python code/measure_reflexion.py --items 2 --tag smoke # quick smoke test (writes part3_smoke_* files)
"""

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_cases import load_cases  # noqa: E402
from agent_loop import quiet_noisy_loggers, run_agent  # noqa: E402
from agent_verifiers import disagreement, ground_truth_extended, oracle  # noqa: E402
from model_client import ModelClient  # noqa: E402
from reflexion import ReflectionStore, run_with_reflexion  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "reports" / "hw07" / "raw"
SEED, TEMPERATURE = 9871, 0.7
MAX_TOOL_CALLS, MAX_TOKENS = 10, 15000


def mean(xs):
    return round(statistics.fmean(xs), 2) if xs else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=12)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    stem = "part3_" + (args.tag + "_" if args.tag else "")
    quiet_noisy_loggers()
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"Run at {started} | qwen3:8b, temperature {TEMPERATURE}, seeds {SEED}+item, {args.items} items per case, "
          f"budgets: {MAX_TOOL_CALLS} tool calls / {MAX_TOKENS} tokens / 2 retries", flush=True)

    truth = ground_truth_extended()
    universe = truth["team_names"]
    store = ReflectionStore(RAW / f"{stem}reflections.jsonl")
    reflect_model = ModelClient(model="qwen3:8b", temperature=0.0, reasoning=False, seed=SEED)
    log_path = RAW / f"{stem}agent_runs.jsonl"
    items, attempts_out = [], []

    for case in load_cases():
        for i in range(args.items):
            seed = SEED + i
            model = ModelClient(model="qwen3:8b", temperature=TEMPERATURE, reasoning=False, seed=seed)
            first = run_agent(case["prompt"], model=model, max_tool_calls=MAX_TOOL_CALLS, max_total_tokens=MAX_TOKENS,
                              log_path=log_path)
            res = run_with_reflexion(
                case, lambda idx, s=seed: ModelClient(model="qwen3:8b", temperature=TEMPERATURE, reasoning=False,
                                                     seed=s + 1000 * idx),
                universe, reflect_model=reflect_model, store=store, max_tool_calls=MAX_TOOL_CALLS,
                max_total_tokens=MAX_TOKENS, first_run=first, log_path=log_path)
            for a in res["attempts"]:
                ok = oracle(case["id"], a["final_answer"], truth)
                attempts_out.append({"case": case["id"], "item": i, "attempt": a["index"], "verifier_pass": a["passed"],
                                     "oracle_correct": ok, "disagreement": disagreement(a["passed"], ok),
                                     "unsupported_claims": a["unsupported_claims"],
                                     "failed_claims": [c["id"] for c in a["claims"] if not c["supported"]],
                                     "tool_calls": a["tool_calls_total"], "tokens": a["tokens"], "latency_ms": a["latency_ms"],
                                     "final_answer": a["final_answer"]})
            a0 = res["attempts"][0]
            orig_ok = oracle(case["id"], a0["final_answer"], truth)
            refl_ok = oracle(case["id"], res["final_answer"], truth)
            t = res["totals"]
            row = {"case": case["id"], "item": i, "seed": seed,
                   "orig_verifier_pass": a0["passed"], "orig_oracle_correct": orig_ok,
                   "orig_unsupported": a0["unsupported_claims"], "orig_tool_calls": a0["tool_calls_total"],
                   "orig_tokens": a0["tokens"], "orig_latency_ms": a0["latency_ms"],
                   "refl_verifier_pass": res["final_passed"], "refl_oracle_correct": refl_ok,
                   "refl_unsupported": res["final_unsupported_claims"], "refl_retries": res["retries"],
                   "refl_tool_calls": t["tool_calls_total"], "refl_tokens": t["tokens"], "refl_latency_ms": t["latency_ms"],
                   "stop_reason": res["stop_reason"]}
            items.append(row)
            print(f"case {case['id']} item {i:>2} seed {seed}: original verifier={'PASS' if row['orig_verifier_pass'] else 'FAIL'} "
                  f"oracle={'ok' if orig_ok else 'WRONG'} | reflexion retries={res['retries']} stop={res['stop_reason']} "
                  f"oracle={'ok' if refl_ok else 'WRONG'} tokens {a0['tokens']}->{t['tokens']}", flush=True)

    def arm(prefix, rows):
        n = len(rows)
        return {
            "runs": n,
            "task_success_oracle": sum(r[f"{prefix}_oracle_correct"] for r in rows),
            "task_success_verifier": sum(r[f"{prefix}_verifier_pass"] for r in rows),
            "unsupported_claims_total": sum(r[f"{prefix}_unsupported"] for r in rows),
            "retry_rate": round(sum(r["refl_retries"] > 0 for r in rows) / n, 3) if prefix == "refl" and n else 0.0,
            "mean_tool_calls": mean([r[f"{prefix}_tool_calls"] for r in rows]),
            "mean_tokens": mean([r[f"{prefix}_tokens"] for r in rows]),
            "mean_latency_ms": mean([r[f"{prefix}_latency_ms"] for r in rows]),
        }

    summary = {"started": started, "model": "qwen3:8b", "temperature": TEMPERATURE, "seed_base": SEED, "items_per_case": args.items,
               "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_total_tokens": MAX_TOKENS, "max_retries": 2},
               "overall": {"original": arm("orig", items), "reflexion": arm("refl", items)},
               "per_case": {c: {"original": arm("orig", [r for r in items if r["case"] == c]),
                                "reflexion": arm("refl", [r for r in items if r["case"] == c])} for c in sorted({r["case"] for r in items})},
               "stop_reasons": {s: sum(r["stop_reason"] == s for r in items) for s in sorted({r["stop_reason"] for r in items})},
               "verifier_vs_oracle_all_attempts": {
                   "attempts_judged": len(attempts_out),
                   "false_rejections": sum(a["disagreement"] == "false_rejection" for a in attempts_out),
                   "false_acceptances": sum(a["disagreement"] == "false_acceptance" for a in attempts_out)},
               "disagreements": [{k: a[k] for k in ("case", "item", "attempt", "disagreement", "failed_claims", "final_answer")}
                                 for a in attempts_out if a["disagreement"]]}

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{stem}attempts.json").write_text(json.dumps(attempts_out, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    (RAW / f"{stem}summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    with (RAW / f"{stem}items.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(items[0]))
        w.writeheader()
        w.writerows(items)

    print("\n=== COMPARISON (paired: same attempt 0 for both arms) ===")
    for label, key in (("overall", None), *[(f"case {c}", c) for c in summary["per_case"]]):
        o, r = ((summary["overall"]["original"], summary["overall"]["reflexion"]) if key is None
                else (summary["per_case"][key]["original"], summary["per_case"][key]["reflexion"]))
        print(f"{label:<9} runs={o['runs']:>3} | success(oracle) {o['task_success_oracle']:>3} -> {r['task_success_oracle']:>3} | "
              f"unsupported {o['unsupported_claims_total']:>3} -> {r['unsupported_claims_total']:>3} | retry rate {r['retry_rate']:.2f} | "
              f"tool calls {o['mean_tool_calls']} -> {r['mean_tool_calls']} | tokens {o['mean_tokens']} -> {r['mean_tokens']} | "
              f"latency ms {o['mean_latency_ms']} -> {r['mean_latency_ms']}")
    v = summary["verifier_vs_oracle_all_attempts"]
    print(f"verifier vs oracle over {v['attempts_judged']} attempts: false rejections={v['false_rejections']}, "
          f"false acceptances={v['false_acceptances']}")
    print(f"stop reasons: {summary['stop_reasons']}")
    print(f"wrote {RAW / (stem + 'summary.json')}")


if __name__ == "__main__":
    main()
