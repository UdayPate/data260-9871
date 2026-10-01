"""
DATA-260 Homework 5 - Part 5.IV: run >=4 real scenarios against the local
Ollama model (qwen3:8b) and record step count / stop reason / tool-call
count for each. Appends to the real reports/hw05/raw/agent_runs.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import run_agent

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "reports" / "hw05" / "raw"

SCENARIOS = [
    {
        "label": "A - detail lookup, normal completion",
        "user_input": "What is the fixture_code and spots_available for fixture id 4?",
        "max_steps": 5,
    },
    {
        "label": "B - aggregate, normal completion",
        "user_input": "Use team_fixture_counts to find teams hosting at least 400 fixtures, "
                      "then tell me which team hosts the most.",
        "max_steps": 5,
    },
    {
        "label": "C - safety rule block",
        "user_input": "Call search_fixtures with the query set to exactly the single "
                      "letter 'a' and tell me what happens.",
        "max_steps": 5,
    },
    {
        "label": "D - max_steps ceiling (forced: max_steps=1 leaves no room "
                  "for a final answer after the tool call)",
        "user_input": "Look up fixture id 10 and summarize it for me.",
        "max_steps": 1,
    },
]


def main():
    results = []
    for sc in SCENARIOS:
        print(f"\n=== Scenario {sc['label']} ===")
        print(f"input: {sc['user_input']!r}  max_steps={sc['max_steps']}")
        r = run_agent(sc["user_input"], max_steps=sc["max_steps"])
        print(f"-> stop_reason={r['stop_reason']}  steps={r['steps']}  "
              f"tool_call_count={r['tool_call_count']}")
        if r["final_answer"]:
            print(f"   final_answer: {r['final_answer'][:200]}")
        results.append({"scenario": sc["label"], **r})

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "part5_agent_scenarios.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8", newline="\n")
    print(f"\nwrote {len(results)} scenario summaries to {out}")


if __name__ == "__main__":
    main()
