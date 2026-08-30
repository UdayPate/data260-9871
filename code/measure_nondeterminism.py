"""
DATA-260 Homework 1 - Part 3: Measuring Non-Determinism
Runs the Planner -> Reviewer -> Finalizer pipeline on a single fixed input
20 times at temperature 0.7 and 20 times at temperature 0.0, records the
final tags and latency for each run, saves the raw results, and computes
summary statistics (distinct tag sets, tags in all runs, tags in exactly
one run, latency p50/p95/p99).
"""

import csv
import json
import statistics
import time
from pathlib import Path

from langchain_ollama import ChatOllama

from agents_demo import run_planner, run_reviewer, finalize

# ---- Paths -----------------------------------------------------------
THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
CASES_DIR = REPO_ROOT / "reports" / "hw01" / "cases"
RAW_DIR = REPO_ROOT / "reports" / "hw01" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = CASES_DIR / "nondeterminism_input.json"
RUNS_PER_TEMPERATURE = 20
TEMPERATURES = [0.7, 0.0]


def load_fixed_input():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["title"], data["content"]


def run_once(title, content, temperature):
    """Run the full pipeline once at the given temperature. Returns (tags, latency_ms)."""
    llm = ChatOllama(model="qwen3:8b", temperature=temperature)

    start = time.perf_counter()
    planner_raw = run_planner(title, content, llm=llm)
    reviewer_raw = run_reviewer(planner_raw, title, content, llm=llm)
    result = finalize(reviewer_raw)
    end = time.perf_counter()

    latency_ms = (end - start) * 1000
    return result["tags"], latency_ms


def percentile(values, pct):
    """Simple percentile using linear interpolation, no numpy dependency."""
    if not values:
        return None
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    return values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f)


def summarize(runs):
    """runs: list of (tags_list, latency_ms). Returns a stats dict."""
    tag_sets = [tuple(sorted(t)) for t, _ in runs]
    distinct_tag_sets = len(set(tag_sets))

    # Flatten tag occurrences across the 20 runs
    tag_run_counts = {}
    for tags, _ in runs:
        for tag in set(tags):  # count each tag once per run, even if repeated
            tag_run_counts[tag] = tag_run_counts.get(tag, 0) + 1

    n_runs = len(runs)
    tags_in_all_runs = sorted([t for t, c in tag_run_counts.items() if c == n_runs])
    tags_in_exactly_one_run = sorted([t for t, c in tag_run_counts.items() if c == 1])

    latencies = [lat for _, lat in runs]

    return {
        "distinct_tag_sets": distinct_tag_sets,
        "tags_in_all_runs": tags_in_all_runs,
        "tags_in_exactly_one_run": tags_in_exactly_one_run,
        "latency_p50_ms": round(percentile(latencies, 50), 1),
        "latency_p95_ms": round(percentile(latencies, 95), 1),
        "latency_p99_ms": round(percentile(latencies, 99), 1),
        "latency_mean_ms": round(statistics.mean(latencies), 1),
    }


def main():
    title, content = load_fixed_input()
    print(f"Fixed input title: {title}\n")

    all_results = {}

    for temperature in TEMPERATURES:
        print(f"=== Running {RUNS_PER_TEMPERATURE} runs at temperature {temperature} ===")
        runs = []
        raw_rows = []

        for i in range(1, RUNS_PER_TEMPERATURE + 1):
            tags, latency_ms = run_once(title, content, temperature)
            runs.append((tags, latency_ms))
            raw_rows.append({
                "run": i,
                "temperature": temperature,
                "tags": tags,
                "latency_ms": round(latency_ms, 1),
            })
            print(f"  run {i:2d}: tags={tags}  latency={latency_ms:.1f}ms")

        # Save raw per-run results for this temperature
        temp_label = str(temperature).replace(".", "_")
        raw_json_path = RAW_DIR / f"nondeterminism_temp_{temp_label}.json"
        raw_csv_path = RAW_DIR / f"nondeterminism_temp_{temp_label}.csv"

        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_rows, f, indent=2)

        with open(raw_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["run", "temperature", "tags", "latency_ms"])
            writer.writeheader()
            for row in raw_rows:
                writer.writerow({**row, "tags": json.dumps(row["tags"])})

        stats = summarize(runs)
        all_results[temperature] = stats

        print(f"\n  Summary for temperature {temperature}:")
        print(json.dumps(stats, indent=4))
        print()

    # Save the combined summary stats for both temperatures
    summary_path = RAW_DIR / "nondeterminism_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in all_results.items()}, f, indent=2)

    print(f"Raw per-run results and summary saved to {RAW_DIR}")


if __name__ == "__main__":
    main()