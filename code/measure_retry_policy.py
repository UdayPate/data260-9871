"""
DATA-260 Homework 5 - Part 3.19/3.20.

Part 3.19: demonstrates the three required retry scenarios (success on
first attempt; failure then success on retry; failure after all retries).

Part 3.20: VERIFY_SEED-driven fault injection at 0%, 20%, 50% injected
failure rates, 50 calls each (150 total). Re-seeding `random.Random(VERIFY_SEED)`
at the start of each rate block makes the success/failure sequence for that
rate reproducible on every run, independent of the others.

Run from code/, inside the venv:
    python measure_retry_policy.py
"""

import json
import random
import statistics
import sys
import time
from pathlib import Path

from retry_policy import SimulatedFailure, call_with_retry

VERIFY_SEED = 269871
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "reports" / "hw05" / "raw"


# ---------------------------------------------------------------------
# Part 3.19 - the three required demo scenarios
# ---------------------------------------------------------------------

def demo_success_first_try():
    return call_with_retry(lambda: {"status": "ok"}, max_retries=3, timeout_s=2.0)


def demo_fail_then_succeed():
    state = {"n": 0}

    def op():
        state["n"] += 1
        if state["n"] == 1:
            raise SimulatedFailure("transient failure on first attempt")
        return {"status": "ok", "succeeded_on_attempt": state["n"]}

    return call_with_retry(op, max_retries=3, base_delay_s=0.05, timeout_s=2.0)


def demo_fail_always():
    def op():
        raise SimulatedFailure("operation always fails")

    return call_with_retry(op, max_retries=3, base_delay_s=0.02, timeout_s=2.0)


# ---------------------------------------------------------------------
# Part 3.20 - VERIFY_SEED fault injection
# ---------------------------------------------------------------------

def run_rate(rate: float, n: int = 50) -> tuple[list[dict], dict]:
    rng = random.Random(VERIFY_SEED)
    records = []
    for i in range(n):
        def op(rng=rng, rate=rate):
            time.sleep(rng.uniform(0.005, 0.02))  # small simulated I/O latency
            if rng.random() < rate:
                raise SimulatedFailure(f"simulated failure (rate={rate})")
            return {"status": "ok"}

        r = call_with_retry(op, max_retries=3, base_delay_s=0.05, max_delay_s=1.0, timeout_s=2.0)
        r["call_index"] = i
        r["injected_failure_rate"] = rate
        records.append(r)

    latencies = [r["latency_ms"] for r in records]
    successes = sum(1 for r in records if r["ok"])
    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 2 else latencies[0]
    summary = {
        "injected_failure_rate": rate,
        "calls": n,
        "success_rate": successes / n,
        "mean_latency_ms": statistics.mean(latencies),
        "p99_latency_ms": p99,
    }
    return records, summary


def main():
    print("=== Part 3.19: required demo scenarios ===")
    r1 = demo_success_first_try()
    print("1. success on first attempt:", json.dumps(r1))
    assert r1["ok"] and r1["attempts"] == 1

    r2 = demo_fail_then_succeed()
    print("2. failure then success on retry:", json.dumps(r2))
    assert r2["ok"] and r2["attempts"] == 2

    r3 = demo_fail_always()
    print("3. failure after all retries:", json.dumps(r3))
    assert not r3["ok"] and r3["attempts"] == 4 and r3["error"]

    print("\n=== Part 3.20: VERIFY_SEED fault injection, 150 calls ===")
    print(f"VERIFY_SEED = {VERIFY_SEED}")
    all_records = []
    summaries = []
    for rate in (0.0, 0.2, 0.5):
        records, summary = run_rate(rate)
        all_records.extend(records)
        summaries.append(summary)
        print(
            f"rate={rate:.0%}: success_rate={summary['success_rate']:.0%}  "
            f"mean={summary['mean_latency_ms']:.1f}ms  p99={summary['p99_latency_ms']:.1f}ms"
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "part3_fault_injection_calls.json").write_text(
        json.dumps(all_records, indent=2), encoding="utf-8", newline="\n"
    )
    (RAW_DIR / "part3_fault_injection_summary.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8", newline="\n"
    )
    print(f"\nwrote {len(all_records)} call records + summary to reports/hw05/raw/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
