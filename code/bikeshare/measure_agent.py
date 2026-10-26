"""
DATA-260 Homework 7 - Part 4: how reliable is the agent? Run each acceptance scenario N times (same settings: qwen3:8b, temperature 0,
seed 9871, thinking off) against the LIVE pricing page and score every run with the independent recomputation in costs.py.

    python code/bikeshare/measure_agent.py --runs 5

Writes reports/hw07/raw/part4_measure_runs.json (every run, with its timeline), part4_measure_runs.csv and part4_measure_summary.json.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import REPO_ROOT, run_bike_agent  # noqa: E402

URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
DATA = Path(__file__).resolve().parent / "data"
RAW = REPO_ROOT / "reports" / "hw07" / "raw"
SCENARIOS = {"membership_wins": DATA / "scenario_membership_wins.csv", "payperuse_wins": DATA / "scenario_payperuse_wins.csv"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    stem = "part4_" + (args.tag + "_" if args.tag else "")
    print("Run at", time.strftime("%Y-%m-%dT%H:%M:%S"), f"| qwen3:8b thinking off, temperature 0, seed 9871 | {args.runs} runs per scenario | {URL}", flush=True)
    runs, rows = [], []
    for i in range(args.runs):
        for name, path in SCENARIOS.items():
            out = run_bike_agent(path, URL, run_id=f"{stem}{name}_{i + 1}", scenario=name)
            v, r = out["verification"], out["result"]
            row = {"scenario": name, "run": i + 1, "stop_reason": out["stop_reason"], "steps": out["steps"], "time_s": out["total_time_s"],
                   "tool_calls": out["tool_calls"]["calls"], "failed_tool_calls": out["tool_calls"]["failed"],
                   "repairs": sum(e["kind"] == "repair" for e in out["timeline"]),
                   "decision": r["decision"] if r else None, "reference_decision": out["reference"]["decision"],
                   "decision_correct": bool(v.get("checks", {}).get("decision")),
                   "all_numbers_correct": bool(v.get("all_ok")),
                   "failed_checks": ",".join(k for k, ok in v.get("checks", {}).items() if not ok),
                   "citations": len(out["citations"]), "citations_found": sum(c["found_in_snapshot"] for c in out["citations"]),
                   "snapshot_sha256": out["snapshot"]["sha256"] if out["snapshot"] else None}
            rows.append(row)
            runs.append(out)
            print(f"{name:16} run {i + 1}: stop={row['stop_reason']} steps={row['steps']} {row['time_s']}s decision_correct={row['decision_correct']} "
                  f"all_numbers_correct={row['all_numbers_correct']} failed_checks=[{row['failed_checks']}] repairs={row['repairs']}", flush=True)
    summary = {"url": URL, "runs_per_scenario": args.runs, "per_scenario": {}, "snapshot_hashes": sorted({r["snapshot_sha256"] for r in rows if r["snapshot_sha256"]})}
    for name in SCENARIOS:
        rs = [r for r in rows if r["scenario"] == name]
        summary["per_scenario"][name] = {
            "runs": len(rs), "final_answer": sum(r["stop_reason"] == "final_answer" for r in rs),
            "decision_correct": sum(r["decision_correct"] for r in rs), "all_numbers_correct": sum(r["all_numbers_correct"] for r in rs),
            "runs_needing_repair": sum(r["repairs"] > 0 for r in rs), "mean_steps": round(statistics.fmean(r["steps"] for r in rs), 1),
            "mean_time_s": round(statistics.fmean(r["time_s"] for r in rs), 1), "mean_failed_tool_calls": round(statistics.fmean(r["failed_tool_calls"] for r in rs), 2),
            "failed_check_counts": {k: sum(k in r["failed_checks"].split(",") for r in rs) for k in ("decision", "pay_per_use_total", "membership_total", "months", "break_even_rides_per_month")}}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{stem}measure_runs.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    (RAW / f"{stem}measure_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    with (RAW / f"{stem}measure_runs.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
