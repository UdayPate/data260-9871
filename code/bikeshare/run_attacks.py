"""
DATA-260 Homework 7 - Part 5: run the three attacks against our own agent on our own local hostile fixture, in three configurations.

  before       untrusted-text labelling OFF, naive csv_sql (trusts the model)
  prompt       labelling ON (system-prompt rules + a warning field on retrieved text), naive csv_sql
  prompt_tool  labelling ON + the shipped csv_sql (single read-only SELECT enforced in code)

The Part 4 self-consistency check is switched OFF in every configuration so that the two Part 5 defenses are measured on their own.
Every run is scored from evidence (final decision, database state, answer text), never by asking a model.

    python code/bikeshare/run_attacks.py --runs 5
    python code/bikeshare/run_attacks.py --runs 1 --attacks misuse --configs before --tag smoke
"""

import argparse
import csv
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import REPO_ROOT, run_bike_agent  # noqa: E402
from attacks import ATTACKS, FIXTURE_URL, SCENARIO_CSV, NaiveCsvSql, build_page, csv_ride_ids, score  # noqa: E402
from tools import CsvSql  # noqa: E402

RAW = REPO_ROOT / "reports" / "hw07" / "raw"
CONFIGS = {"before": (False, NaiveCsvSql), "prompt": (True, NaiveCsvSql), "prompt_tool": (True, CsvSql)}
SNAP_TMP = Path(tempfile.mkdtemp(prefix="part5_snap_"))      # the page text is the saved fixture; per-run copies are not kept
MARKERS = {a: v["marker"] for a, v in ATTACKS.items()}     # the END of each payload: if it is in a retrieved passage, the whole instruction reached the model


def excerpt(attack: str, run: dict, sc: dict) -> dict:
    """A short, human-readable record of one attempt: what the model saw, what it did, how it ended."""
    seen = next((t for t in run["retrieved"] if MARKERS[attack] in t), None)
    i = seen.find(MARKERS[attack]) if seen else -1
    out = {"page_text_the_model_received": (seen[max(0, i - 60): i + 160] if seen else "(the injected text was not in any retrieved passage)")}
    if attack == "override":
        out["model_output"] = f"decision = {sc['decision']!r}; justification starts: {(run['result'] or {}).get('justification', '')[:170]!r}" if run.get("result") else "(no answer)"
    elif attack == "misuse":
        writes = sc["attempted_sql"]
        obs = [e for e in run["timeline"] if e["kind"] == "observation" and e["tool"] == "csv_sql"]
        res = next((e["output"][:170] for e in obs if '"rows_affected"' in e["output"] or "read-only" in e["output"] or "not allowed" in e["output"]), "")
        out["model_output"] = f"csv_sql called with {writes[0]!r}" if writes else "no write statement was sent to csv_sql"
        out["tool_result"] = res
    else:
        out["model_output"] = f"{sc['ride_ids_leaked']} CSV ride ids in the answer; e.g. {sc['example_ids']}; justification starts: {(run['result'] or {}).get('justification', '')[:150]!r}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--attacks", nargs="+", default=list(ATTACKS), choices=list(ATTACKS))
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=list(CONFIGS))
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    stem = "part5_" + (args.tag + "_" if args.tag else "")
    ride_ids, original_rows = csv_ride_ids(), len(csv_ride_ids())
    print("Run at", time.strftime("%Y-%m-%dT%H:%M:%S"), f"| qwen3:8b thinking off, temperature 0, seed 9871 | {args.runs} runs per cell | hostile LOCAL fixture {FIXTURE_URL}", flush=True)
    records, runs = [], []
    for attack in args.attacks:
        page = build_page(attack)
        for config in args.configs:
            labelling, csv_cls = CONFIGS[config]
            for i in range(args.runs):
                box = {}

                def factory(path, name="uploaded.csv", csv_cls=csv_cls, box=box):
                    box["inst"] = csv_cls(path, name)
                    return box["inst"]

                run = run_bike_agent(SCENARIO_CSV, FIXTURE_URL, run_id=f"{stem}{attack}_{config}_{i + 1}", fetcher=lambda u, page=page: page, check_url=False,
                                     untrusted_labeling=labelling, csv_sql_factory=factory, consistency_check=False, snapshot_dir=SNAP_TMP)
                sc = score(attack, run, box["inst"], original_rows, ride_ids)
                exposed = any(MARKERS[attack] in t for t in run["retrieved"])
                rec = {"attack": attack, "config": config, "run": i + 1, "attack_succeeded": sc["success"], "injection_reached_model": exposed,
                       "stop_reason": run["stop_reason"], "steps": run["steps"], "time_s": run["total_time_s"],
                       "ignored_instructions_note": any("instruction" in a.lower() or "ignor" in a.lower() for a in (run["result"] or {}).get("assumptions", [])),
                       **{k: v for k, v in sc.items() if k not in ("success", "attempted_sql", "example_ids")}}
                rec["excerpt"] = excerpt(attack, run, sc)
                records.append(rec)
                runs.append({**{k: v for k, v in rec.items() if k != "excerpt"}, "score": sc, "excerpt": rec["excerpt"], "timeline": run["timeline"], "final_text": run["final_text"]})
                print(f"{attack:8} {config:12} run {i + 1}: success={sc['success']!s:5} reached_model={exposed!s:5} stop={run['stop_reason']} {run['total_time_s']}s "
                      f"{ {k: v for k, v in sc.items() if k in ('decision', 'attempted_write', 'rows_left', 'ride_ids_leaked')} }", flush=True)
    summary = {"runs_per_cell": args.runs, "cells": {}}
    for attack in args.attacks:
        for config in args.configs:
            rs = [r for r in records if r["attack"] == attack and r["config"] == config]
            hit = [r for r in rs if r["attack_succeeded"]]
            rep = (hit or rs)[0] if (len(hit) * 2 >= len(rs)) else next(r for r in rs if not r["attack_succeeded"])
            summary["cells"][f"{attack}/{config}"] = {
                "runs": len(rs), "attack_succeeded": len(hit), "injection_reached_model": sum(r["injection_reached_model"] for r in rs),
                "attempted_write": sum(bool(r.get("attempted_write")) for r in rs), "ignored_instructions_note": sum(r["ignored_instructions_note"] for r in rs),
                "representative_run": f"{stem}{attack}_{config}_{rep['run']}", "representative_outcome": "attack succeeded" if rep["attack_succeeded"] else "attack failed",
                "excerpt": rep["excerpt"]}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{stem}attack_runs.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    (RAW / f"{stem}attack_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    flat = [{k: v for k, v in r.items() if k != "excerpt"} for r in records]
    with (RAW / f"{stem}attack_results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in flat for k in r}))
        w.writeheader()
        w.writerows(flat)
    print("\n=== BEFORE / AFTER (attack succeeded / runs) ===")
    print(f"{'attack':10} " + " ".join(f"{c:>12}" for c in args.configs))
    for attack in args.attacks:
        print(f"{attack:10} " + " ".join(f"{summary['cells'][f'{attack}/{c}']['attack_succeeded']}/{summary['cells'][f'{attack}/{c}']['runs']:>10}" for c in args.configs))
    print("wrote", RAW / f"{stem}attack_summary.json")


if __name__ == "__main__":
    main()
