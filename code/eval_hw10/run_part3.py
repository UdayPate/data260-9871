"""
DATA-260 Homework 10 - Part 3.2/3.3: validate the judge against the frozen human labels.

    code\\venv\\Scripts\\python.exe code/eval_hw10/run_part3.py

Runs the Writer Helpfulness judge (judge.py: GEval, qwen3:8b, temperature 0, seed 9871) on the 20 frozen drafts in reports/hw10/eval_cases.json THREE times with
identical inputs and settings, and compares with reports/hw10/human_labels.csv:
  3.2  Spearman rank correlation (human vs judge, run 1) and mean absolute difference (human vs judge, per run),
  3.3  repeatability: share of cases whose score changed between runs, and the mean / maximum absolute change over all run pairs.
Writes raw/part3_judge_scores.json (per-case data for every run, enough to recompute every statistic) and raw/part3_judge_scores.csv.
It does not modify eval_cases.json or human_labels.csv; their SHA-256 are recorded in the output.
"""

import csv
import hashlib
import itertools
import json
import statistics as st
import sys
import time
from datetime import datetime
from pathlib import Path

from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge as jd  # noqa: E402

HW = HERE.parents[1] / "reports" / "hw10"
RUNS = 3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def statistics(human: list[int], runs: list[list[int | None]]) -> dict:
    ok = [i for i in range(len(human)) if all(r[i] is not None for r in runs)]
    h = [human[i] for i in ok]
    rho, p = spearmanr(h, [runs[0][i] for i in ok])
    mad = [round(st.mean(abs(h[k] - r[i]) for k, i in enumerate(ok)), 3) for r in runs]
    changes = [abs(runs[a][i] - runs[b][i]) for a, b in itertools.combinations(range(len(runs)), 2) for i in ok]
    per_case = [max(r[i] for r in runs) - min(r[i] for r in runs) for i in ok]
    return {"n_scored": len(ok), "spearman_rho_run1": round(float(rho), 4), "spearman_p_run1": round(float(p), 4),
            "spearman_rho_per_run": [round(float(spearmanr(h, [r[i] for i in ok])[0]), 4) for r in runs],
            "mean_abs_difference_per_run": mad, "mean_abs_difference_run1": mad[0],
            "mean_judge_minus_mean_human_run1": round(st.mean(runs[0][i] for i in ok) - st.mean(h), 3),
            "exact_agreement_run1_pct": round(100 * sum(runs[0][i] == human[i] for i in ok) / len(ok), 1),
            "within_1_run1_pct": round(100 * sum(abs(runs[0][i] - human[i]) <= 1 for i in ok) / len(ok), 1),
            "cases_with_any_change_across_runs": sum(c > 0 for c in per_case), "cases_with_any_change_pct": round(100 * sum(c > 0 for c in per_case) / len(ok), 1),
            "pairwise_comparisons": len(changes), "pairwise_changed": sum(c > 0 for c in changes),
            "pairwise_changed_pct": round(100 * sum(c > 0 for c in changes) / len(changes), 1),
            "mean_abs_change": round(st.mean(changes), 4), "max_abs_change": max(changes)}


def main() -> int:
    cases_p, labels_p = HW / "eval_cases.json", HW / "human_labels.csv"
    cases = json.loads(cases_p.read_text(encoding="utf-8"))["cases"]
    labels = {r["case_id"]: int(r["human_label"]) for r in csv.DictReader(open(labels_p, encoding="utf-8"))}
    assert [c["case_id"] for c in cases] == list(labels), "cases and labels do not line up"
    human = [labels[c["case_id"]] for c in cases]
    judge = jd.LocalJudge()
    print(f"judge {jd.JUDGE_MODEL} temperature={jd.JUDGE_TEMPERATURE} seed={jd.JUDGE_SEED}; {len(cases)} drafts x {RUNS} runs\n", flush=True)
    runs: list[list[int | None]] = []
    detail: list[list[dict]] = []
    for run in range(1, RUNS + 1):
        scores, rows = [], []
        for c in cases:
            try:
                r = jd.score("writer_helpfulness", judge, c["question"], c["draft"])
                scores.append(r["score"])
                rows.append({"case_id": c["case_id"], **r})
            except jd.JudgeUnavailable as exc:
                scores.append(None)
                rows.append({"case_id": c["case_id"], "score": None, "error": str(exc)})
        runs.append(scores)
        detail.append(rows)
        print(f"run {run}: {scores}", flush=True)
    stats = statistics(human, runs)
    print("\nhuman :", human)
    print(json.dumps(stats, indent=2))
    out = {"part": 3, "run_at": datetime.now().isoformat(timespec="seconds"), "criterion": "Writer Helpfulness (GEval, 5-band rubric)",
           "judge": {"model": jd.JUDGE_MODEL, "temperature": jd.JUDGE_TEMPERATURE, "seed": jd.JUDGE_SEED, "thinking": False, "scale": jd.SCALE},
           "inputs": {"eval_cases_sha256": sha(cases_p), "human_labels_sha256": sha(labels_p)}, "statistics": stats,
           "cases": [{"case_id": c["case_id"], "trace_id": c["trace_id"], "human_label": human[i], "judge_scores": [runs[r][i] for r in range(RUNS)],
                      "judge_reasons": [detail[r][i].get("reason") for r in range(RUNS)], "judge_ms": [detail[r][i].get("judge_ms") for r in range(RUNS)]}
                     for i, c in enumerate(cases)]}
    (HW / "raw" / "part3_judge_scores.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(HW / "raw" / "part3_judge_scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "human_label"] + [f"judge_run{r}" for r in range(1, RUNS + 1)])
        for i, c in enumerate(cases):
            w.writerow([c["case_id"], human[i]] + [runs[r][i] for r in range(RUNS)])
    print(f"\nwrote raw/part3_judge_scores.json and .csv at {time.strftime('%H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
