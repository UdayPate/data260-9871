"""
DATA-260 Homework 4 - Part 3: N+1 measurement script.

Fires 30 real HTTP requests at each of 3 page sizes (10, 50, 200)
against BOTH the naive and fixed endpoints (180 total requests),
recording the real SQL query count (from the X-SQL-Query-Count header
our middleware attaches) and latency for each one.

Run with: python measure_n1.py
"""

import csv
import json
import statistics
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:8871"
EMAIL = "league_admin@example.com"
PASSWORD = "GoLions2026!"
PAGE_SIZES = [10, 50, 200]
VERSIONS = ["naive", "fixed"]
RUNS_PER_COMBO = 30

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "reports" / "hw04" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def percentile(values, pct):
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    return values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f)


def main():
    session = requests.Session()

    print("Logging in...")
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    resp.raise_for_status()
    print(f"  Logged in as: {resp.json()['name']}")

    # requests' cookie jar correctly honors the Secure flag (unlike real
    # browsers, which treat localhost as a special trustworthy exception -
    # see HW3's cookie security work) - so it won't automatically resend
    # our Secure cookie over this plain http:// connection. We bypass that
    # by passing the cookie explicitly on every request instead of relying
    # on the session's automatic cookie jar.
    session_token = session.cookies.get("session_token")
    auth_cookies = {"session_token": session_token}

    all_rows = []

    for version in VERSIONS:
        for page_size in PAGE_SIZES:
            print(f"\nMeasuring: version={version}, page_size={page_size}")
            for run in range(1, RUNS_PER_COMBO + 1):
                start = time.perf_counter()
                resp = session.get(
                    f"{BASE_URL}/api/fixtures-{version}",
                    params={"page_size": page_size},
                    cookies=auth_cookies,
                )
                latency_ms = (time.perf_counter() - start) * 1000
                resp.raise_for_status()

                query_count = int(resp.headers.get("X-SQL-Query-Count", -1))
                num_results = len(resp.json())

                row = {
                    "version": version,
                    "page_size": page_size,
                    "run": run,
                    "sql_query_count": query_count,
                    "latency_ms": round(latency_ms, 2),
                    "num_results": num_results,
                }
                all_rows.append(row)

                if run == 1 or run == RUNS_PER_COMBO:
                    print(f"  run {run:2d}: queries={query_count}  latency={latency_ms:.2f}ms  results={num_results}")

    # Save raw data (all 180 rows)
    raw_json_path = RAW_DIR / "n1_measurements.json"
    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2)

    raw_csv_path = RAW_DIR / "n1_measurements.csv"
    with open(raw_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["version", "page_size", "run", "sql_query_count", "latency_ms", "num_results"])
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    print(f"\n\nRaw data ({len(all_rows)} rows) saved to:")
    print(f"  {raw_json_path}")
    print(f"  {raw_csv_path}")

    # Compute summary table
    summary = []
    for version in VERSIONS:
        for page_size in PAGE_SIZES:
            group = [r for r in all_rows if r["version"] == version and r["page_size"] == page_size]
            latencies = [r["latency_ms"] for r in group]
            query_counts = set(r["sql_query_count"] for r in group)
            summary.append({
                "page_size": page_size,
                "version": version,
                "sql_stmts_per_req": query_counts.pop() if len(query_counts) == 1 else f"varied: {query_counts}",
                "p50_ms": round(percentile(latencies, 50), 2),
                "p95_ms": round(percentile(latencies, 95), 2),
                "p99_ms": round(percentile(latencies, 99), 2),
            })

    summary_path = RAW_DIR / "n1_summary_table.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'Page size':<10}{'Version':<10}{'SQL stmts/req':<15}{'p50 (ms)':<11}{'p95 (ms)':<11}{'p99 (ms)':<11}")
    print("-" * 68)
    for row in summary:
        print(f"{row['page_size']:<10}{row['version']:<10}{str(row['sql_stmts_per_req']):<15}"
              f"{row['p50_ms']:<11}{row['p95_ms']:<11}{row['p99_ms']:<11}")

    print(f"\nSummary saved to: {summary_path}")

    # Speedup comparison
    print(f"\n{'='*68}")
    print("Speedup (naive p50 / fixed p50) per page size:")
    for page_size in PAGE_SIZES:
        naive_row = next(r for r in summary if r["version"] == "naive" and r["page_size"] == page_size)
        fixed_row = next(r for r in summary if r["version"] == "fixed" and r["page_size"] == page_size)
        speedup = naive_row["p50_ms"] / fixed_row["p50_ms"] if fixed_row["p50_ms"] > 0 else float("inf")
        print(f"  page_size={page_size}: naive={naive_row['p50_ms']}ms, fixed={fixed_row['p50_ms']}ms, speedup={speedup:.2f}x")


if __name__ == "__main__":
    main()