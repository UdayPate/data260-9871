"""
DATA-260 Homework 7 - Part 2.III: tool-use reliability measurement.

Runs the three fixed verification cases (A, B, C from agent_cases/verification_cases.json) many times with the SAME
model settings (qwen3:8b, thinking off, temperature 0.7; only the sampling seed changes, 9871 + attempt number) and
reports how often the model's tool calls are well-formed BEFORE and AFTER the repair path, and which failure
categories remain.

Two clearly separate experiments:
  natural - the real tool schemas. Whatever the model does on its own.
  stress  - the model is shown DRIFTED schemas (parameters renamed) while the validator holds the real ones, so
            every first-try call is invalid. This is a deliberate fault injection to measure how much the repair
            path rescues; it says nothing about the model's natural error rate.

Definitions (first-try calls only; a retry made after an invalid call is a repair attempt, not a first try):
  well-formed BEFORE repair = first-try calls that were valid / all first-try calls
  well-formed AFTER repair  = (valid first-try calls + invalid first-try calls the repair path later fixed) / all first-try calls
  attempt clean BEFORE      = no first-try failure of any category
  attempt clean AFTER       = the multi-step chain was completed and every invalid call was repaired

Run from the repo root, inside the venv:   python code/measure_tool_reliability.py [attempts_per_case] [stress_attempts_per_case]
"""

import csv
import json
import statistics as st
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_cases import LOST, MALFORMED, TEXT, UNKNOWN, classify_attempt, drifted_specs, ground_truth, load_cases  # noqa: E402
from agent_loop import quiet_noisy_loggers, run_agent  # noqa: E402
from model_client import ModelClient  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "reports" / "hw07" / "raw"
TEMPERATURE = 0.7
CATEGORIES = [MALFORMED, UNKNOWN, TEXT, LOST]


def run_experiment(label, per_case, offered_specs, truth, log_path):
    cases, rows = load_cases(), []
    for i in range(per_case * len(cases)):
        case, seed = cases[i % len(cases)], 9871 + i
        model = ModelClient(model="qwen3:8b", temperature=TEMPERATURE, reasoning=False, seed=seed)
        out = run_agent(case["prompt"], model=model, log_path=log_path, offered_specs=offered_specs)
        cls = classify_attempt(case["id"], out, truth)
        row = {"experiment": label, "attempt": i + 1, "case": case["id"], "seed": seed, "temperature": TEMPERATURE,
               "stop_reason": out["stop_reason"], "steps": out["steps"], "tool_calls_total": out["tool_calls_total"],
               "tool_calls_executed": out["tool_calls_executed"], "tool_calls_invalid": out["tool_calls_invalid"],
               "invalid_repaired": out["invalid_calls_repaired"], "failed_repairs": out["failed_repairs"],
               "first_try_calls": cls["first_try_calls"], "first_try_invalid": cls["first_try_invalid"],
               "first_try_invalid_rescued": cls["first_try_invalid_rescued"],
               "first_try_failures": "|".join(cls["first_try_failures"]), "final_failure": cls["final_failure"] or "",
               "chain_complete": cls["chain_complete"], "chain_note": cls["chain_note"],
               "prompt_tokens": out["tokens"]["prompt"], "completion_tokens": out["tokens"]["completion"],
               "latency_ms": out["latency_ms"], "final_answer": (out["final_answer"] or "")[:400],
               "trace": out["trace"]}
        rows.append(row)
        print(f"[{label} {i + 1:2d}/{per_case * len(cases)}] case {case['id']} seed {seed}: calls={out['tool_calls_total']} "
              f"invalid={out['tool_calls_invalid']} rescued={out['invalid_calls_repaired']} stop={out['stop_reason']} "
              f"first-try failures={cls['first_try_failures'] or '-'} final={cls['final_failure'] or 'clean'}", flush=True)
    return rows


def summarize(rows):
    n = len(rows)
    first = sum(r["first_try_calls"] for r in rows)
    bad = sum(r["first_try_invalid"] for r in rows)
    rescued = sum(r["first_try_invalid_rescued"] for r in rows)
    before_cats, after_cats = Counter(), Counter()
    for r in rows:
        for c in filter(None, r["first_try_failures"].split("|")):
            before_cats[c] += 1
        if r["final_failure"]:
            after_cats[r["final_failure"]] += 1
    return {
        "attempts": n,
        "attempts_per_case": dict(Counter(r["case"] for r in rows)),
        "first_try_calls": first, "first_try_invalid": bad, "first_try_invalid_rescued": rescued,
        "well_formed_rate_before_repair": round((first - bad) / first, 4) if first else None,
        "well_formed_rate_after_repair": round((first - bad + rescued) / first, 4) if first else None,
        "attempts_clean_before_repair": sum(1 for r in rows if not r["first_try_failures"]),
        "attempts_clean_after_repair": sum(1 for r in rows if not r["final_failure"]),
        "failures_before_repair_by_category": {c: before_cats.get(c, 0) for c in CATEGORIES},
        "failures_after_repair_by_category": {c: after_cats.get(c, 0) for c in CATEGORIES},
        "per_case_clean_after_repair": {k: sum(1 for r in rows if r["case"] == k and not r["final_failure"])
                                        for k in sorted({r["case"] for r in rows})},
        "mean_steps": round(st.fmean(r["steps"] for r in rows), 2),
        "mean_tool_calls": round(st.fmean(r["tool_calls_total"] for r in rows), 2),
        "mean_tokens": round(st.fmean(r["prompt_tokens"] + r["completion_tokens"] for r in rows), 1),
        "mean_latency_ms": round(st.fmean(r["latency_ms"] for r in rows), 1),
        "stop_reasons": dict(Counter(r["stop_reason"] for r in rows)),
    }


def show(title, s):
    pct = lambda x: f"{x * 100:.1f}%" if x is not None else "n/a"
    print(f"\n=== {title} ({s['attempts']} attempts: {s['attempts_per_case']}) ===")
    print(f"first-try tool calls: {s['first_try_calls']}  (invalid: {s['first_try_invalid']}, rescued by repair: {s['first_try_invalid_rescued']})")
    print(f"well-formed call rate   BEFORE repair {pct(s['well_formed_rate_before_repair'])}   AFTER repair {pct(s['well_formed_rate_after_repair'])}")
    print(f"clean attempts          BEFORE repair {s['attempts_clean_before_repair']}/{s['attempts']}   AFTER repair {s['attempts_clean_after_repair']}/{s['attempts']}")
    print(f"{'failure category':28s} {'before repair':>14s} {'after repair':>13s}")
    for c in CATEGORIES:
        print(f"{c:28s} {s['failures_before_repair_by_category'][c]:>14d} {s['failures_after_repair_by_category'][c]:>13d}")
    print(f"mean steps {s['mean_steps']} | tool calls {s['mean_tool_calls']} | tokens {s['mean_tokens']} | latency {s['mean_latency_ms']} ms | stops {s['stop_reasons']}")


def main():
    natural_per_case = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    stress_per_case = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    quiet_noisy_loggers()
    RAW.mkdir(parents=True, exist_ok=True)
    log_path = RAW / "agent_runs_reliability.jsonl"
    print("Run at", time.strftime("%Y-%m-%dT%H:%M:%S"), f"| qwen3:8b thinking off, temperature {TEMPERATURE}, seeds 9871+attempt")
    truth = ground_truth()
    print("ground truth:", {k: v for k, v in truth.items() if k in ("A_first_id", "C_ids")}, "top team:", truth["B_top_team"]["team_name"])

    natural = run_experiment("natural", natural_per_case, None, truth, log_path)
    stress = run_experiment("stress", stress_per_case, drifted_specs(), truth, log_path)
    summary = {"model": "qwen3:8b (Ollama), thinking off", "temperature": TEMPERATURE, "seeds": "9871 + attempt index",
               "natural": summarize(natural), "stress": summarize(stress)}
    show("NATURAL (real schemas)", summary["natural"])
    show("STRESS (drifted schemas shown to the model: deliberate fault injection)", summary["stress"])

    all_rows = natural + stress
    (RAW / "part2_reliability_attempts.json").write_text(json.dumps(all_rows, indent=1), encoding="utf-8")
    (RAW / "part2_reliability_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    cols = [k for k in all_rows[0] if k != "trace"]
    with open(RAW / "part2_reliability_attempts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r[k] for k in cols})
    print("\nwrote raw/part2_reliability_attempts.json / .csv, part2_reliability_summary.json")


if __name__ == "__main__":
    main()
