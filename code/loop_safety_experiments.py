"""
DATA-260 Homework 2 - Part 4: Output Schema and Loop Safety experiments.
Runs three experiments against the LangGraph stateful agent graph
(agent_graph.py):

1. Classification: 30 runs on a fixed input, classified as valid first
   attempt / valid after 1 retry / valid after 2+ retries / hit ceiling.
2. Ceiling comparison: 20 runs at turn_ceiling=2 vs 20 runs at
   turn_ceiling=10, same frozen input - completion rate and mean latency.
3. Adversarial input: one deliberately difficult input, run 5 times.

Results are saved under reports/hw02/raw/ and printed as summaries.
"""

import csv
import json
import statistics
import sys
import time
from pathlib import Path

# code/ is where agent_graph.py lives, alongside this script
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import agent_graph  # noqa: E402
from agent_graph import build_graph, AgentState  # noqa: E402

sys.path.insert(0, str(THIS_DIR.parent / "src"))
from model_client import ModelClient  # noqa: E402


REPO_ROOT = THIS_DIR.parent
CASES_DIR = REPO_ROOT / "reports" / "hw02" / "cases"
RAW_DIR = REPO_ROOT / "reports" / "hw02" / "raw"
CASES_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA_INPUT_FILE = CASES_DIR / "schema_input.json"
ADVERSARIAL_INPUT_FILE = CASES_DIR / "adversarial_input.json"


# ---------------------------------------------------------------------
# Core: run the graph once, return a structured result
# ---------------------------------------------------------------------

def run_once(title: str, content: str, turn_ceiling: int) -> dict:
    """Runs the graph once. Returns planner_call_count, outcome
    ('success' or 'hit_ceiling'), turn_count, and latency_ms."""
    graph = build_graph()
    llm = ModelClient(model="qwen3:8b", temperature=0.7)

    initial_state: AgentState = {
        "title": title,
        "content": content,
        "email": "student@example.com",
        "strict": False,
        "task": "generate_tags_and_summary",
        "llm": llm,
        "planner_proposal": {},
        "reviewer_feedback": {},
        "turn_count": 0,
        "turn_ceiling": turn_ceiling,
        "schema_error": "",
    }

    planner_call_count = 0
    current_state = dict(initial_state)

    start = time.perf_counter()
    for step in graph.stream(initial_state):
        for node_name, updates in step.items():
            if node_name == "planner":
                planner_call_count += 1
            current_state.update(updates)
    end = time.perf_counter()

    latency_ms = (end - start) * 1000

    proposal = current_state.get("planner_proposal") or {}
    feedback = current_state.get("reviewer_feedback") or {}
    success = bool(proposal) and feedback.get("issues") == []

    return {
        "outcome": "success" if success else "hit_ceiling",
        "planner_call_count": planner_call_count,
        "turn_count": current_state.get("turn_count", 0),
        "latency_ms": round(latency_ms, 1),
        "final_proposal": proposal,
    }


def classify(result: dict) -> str:
    if result["outcome"] == "hit_ceiling":
        return "hit_turn_ceiling"
    n = result["planner_call_count"]
    if n <= 1:
        return "valid_first_attempt"
    if n == 2:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"


def percentile(values, pct):
    if not values:
        return None
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    return values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f)


# ---------------------------------------------------------------------
# Experiment 1: 30-run classification
# ---------------------------------------------------------------------

def experiment_1_classification(title, content, n_runs=30, turn_ceiling=6):
    print(f"\n{'='*60}")
    print(f"EXPERIMENT 1: {n_runs}-run classification (turn_ceiling={turn_ceiling})")
    print(f"{'='*60}")

    counts = {
        "valid_first_attempt": {"count": 0, "latencies": []},
        "valid_after_1_retry": {"count": 0, "latencies": []},
        "valid_after_2plus_retries": {"count": 0, "latencies": []},
        "hit_turn_ceiling": {"count": 0, "latencies": []},
    }
    raw_rows = []

    for i in range(1, n_runs + 1):
        result = run_once(title, content, turn_ceiling)
        category = classify(result)
        counts[category]["count"] += 1
        counts[category]["latencies"].append(result["latency_ms"])
        raw_rows.append({"run": i, "category": category, **result})
        print(f"  run {i:2d}: category={category}  "
              f"planner_calls={result['planner_call_count']}  "
              f"latency={result['latency_ms']:.1f}ms")

    # Save raw results
    raw_path = RAW_DIR / "schema_validation_30runs.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_rows, f, indent=2, default=str)

    csv_path = RAW_DIR / "schema_validation_30runs.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["run", "category", "outcome",
                                                 "planner_call_count", "turn_count", "latency_ms"])
        writer.writeheader()
        for row in raw_rows:
            writer.writerow({k: row[k] for k in writer.fieldnames})

    # Summary table
    summary = {}
    for cat, data in counts.items():
        mean_lat = round(statistics.mean(data["latencies"]), 1) if data["latencies"] else None
        summary[cat] = {"count": data["count"], "mean_latency_ms": mean_lat}

    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    return summary


# ---------------------------------------------------------------------
# Experiment 2: ceiling comparison (2 vs 10)
# ---------------------------------------------------------------------

def experiment_2_ceiling_comparison(title, content, n_runs=20):
    print(f"\n{'='*60}")
    print(f"EXPERIMENT 2: Ceiling comparison ({n_runs} runs each, ceiling=2 vs ceiling=10)")
    print(f"{'='*60}")

    results_by_ceiling = {}

    for ceiling in [2, 10]:
        print(f"\n--- turn_ceiling = {ceiling} ---")
        raw_rows = []
        for i in range(1, n_runs + 1):
            result = run_once(title, content, ceiling)
            raw_rows.append({"run": i, "turn_ceiling": ceiling, **result})
            print(f"  run {i:2d}: outcome={result['outcome']}  latency={result['latency_ms']:.1f}ms")

        successes = [r for r in raw_rows if r["outcome"] == "success"]
        completion_rate = len(successes) / n_runs
        latencies = [r["latency_ms"] for r in raw_rows]
        mean_latency = round(statistics.mean(latencies), 1)

        results_by_ceiling[ceiling] = {
            "completion_rate": round(completion_rate, 3),
            "mean_latency_ms": mean_latency,
            "raw_rows": raw_rows,
        }

        raw_path = RAW_DIR / f"ceiling_comparison_ceiling_{ceiling}.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw_rows, f, indent=2, default=str)

    summary = {
        str(ceiling): {
            "completion_rate": data["completion_rate"],
            "mean_latency_ms": data["mean_latency_ms"],
        }
        for ceiling, data in results_by_ceiling.items()
    }
    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    return summary


# ---------------------------------------------------------------------
# Experiment 3: adversarial input
# ---------------------------------------------------------------------

def experiment_3_adversarial(title, content, n_runs=5, turn_ceiling=6):
    print(f"\n{'='*60}")
    print(f"EXPERIMENT 3: Adversarial input, {n_runs} runs (turn_ceiling={turn_ceiling})")
    print(f"{'='*60}")

    raw_rows = []
    for i in range(1, n_runs + 1):
        result = run_once(title, content, turn_ceiling)
        raw_rows.append({"run": i, **result})
        print(f"  run {i}: outcome={result['outcome']}  "
              f"planner_calls={result['planner_call_count']}  "
              f"latency={result['latency_ms']:.1f}ms")

    ceiling_hits = sum(1 for r in raw_rows if r["outcome"] == "hit_ceiling")
    observed_rate = ceiling_hits / n_runs

    raw_path = RAW_DIR / "adversarial_5runs.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_rows, f, indent=2, default=str)

    print(f"\nCeiling hit rate: {ceiling_hits}/{n_runs} ({observed_rate*100:.0f}%)")
    return {"ceiling_hits": ceiling_hits, "n_runs": n_runs, "observed_rate": observed_rate}


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    # Load the fixed schema-validation input
    with open(SCHEMA_INPUT_FILE, "r", encoding="utf-8") as f:
        schema_input = json.load(f)

    with open(ADVERSARIAL_INPUT_FILE, "r", encoding="utf-8") as f:
        adversarial_input = json.load(f)

    all_summaries = {}

    all_summaries["experiment_1"] = experiment_1_classification(
        schema_input["title"], schema_input["content"]
    )
    all_summaries["experiment_2"] = experiment_2_ceiling_comparison(
        schema_input["title"], schema_input["content"]
    )
    all_summaries["experiment_3"] = experiment_3_adversarial(
        adversarial_input["title"], adversarial_input["content"]
    )

    summary_path = RAW_DIR / "part4_all_summaries.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, default=str)

    print(f"\n\nAll Part 4 experiments complete. Summaries saved to {summary_path}")


if __name__ == "__main__":
    main()