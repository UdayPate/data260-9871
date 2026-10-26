"""
DATA-260 Homework 7 - Part 4: run the agent once from the command line (no UI) and print the timeline and the verification.

    python code/bikeshare/run_one.py code/bikeshare/data/scenario_membership_wins.csv [pricing_url]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import default_model, run_bike_agent  # noqa: E402

URL = "https://www.lyft.com/bikes/bay-wheels/pricing"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv_path = args[0]
    url = args[1] if len(args) > 1 else URL
    out = run_bike_agent(csv_path, url, model=default_model(thinking="--thinking" in sys.argv), on_event=lambda e: print(
        f"[{e['t_ms'] / 1000:6.1f}s step {e['step']}] {e['kind'].upper():11} "
        f"{e.get('tool', '')} {json.dumps(e.get('input', e.get('text', e.get('output', ''))))[:230]}", flush=True))
    print(f"\nstop_reason={out['stop_reason']} steps={out['steps']} time={out['total_time_s']}s tool_calls={out['tool_calls']} tokens={out['tokens']}")
    if out["error"] or out["problem"]:
        print("error/problem:", out["error"] or out["problem"])
    if out["result"]:
        r = out["result"]
        print("decision:", r["decision"], "| costs:", r["costs"], "| break_even:", r["break_even"])
        print("justification:", r["justification"])
        print("citations:", out["citations"])
    print("verification:", json.dumps(out["verification"]))
    print("snapshot:", json.dumps(out["snapshot"]))


if __name__ == "__main__":
    main()
