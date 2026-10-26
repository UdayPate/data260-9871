"""
DATA-260 Homework 7 - Part 4: write reports/hw07/part4/EVIDENCE.md from the two UI acceptance runs saved in reports/hw07/raw/part4_runs/,
after removing every other pricing snapshot in reports/hw07/part4/snapshots/ (the measurement runs' hashes are kept in their summary JSON).
Every kept snapshot is re-hashed and must match the SHA-256 recorded when it was taken.

    python code/bikeshare/make_evidence_index.py
"""

import hashlib
import json
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent.parent / "reports" / "hw07"
LABELS = {"scenario_membership_wins.csv": "Membership wins", "scenario_payperuse_wins.csv": "Pay-per-use wins"}


def main():
    runs = {}
    for f in sorted((REPORT / "raw" / "part4_runs").glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        runs[r["csv"]] = r
    missing = [c for c in LABELS if c not in runs]
    if missing:
        sys.exit(f"missing acceptance runs for: {missing}")
    keep = set()
    for r in runs.values():
        keep |= {f"{r['run_id']}_pricing.txt", f"{r['run_id']}_pricing.meta.json"}
    snaps = REPORT / "part4" / "snapshots"
    for f in snaps.glob("*"):
        if f.name not in keep:
            f.unlink()
    md = ("# Part 4 - saved pricing-page evidence\n\n"
          "Each acceptance run fetched the live page, froze the extracted text, and hashed it. The agent searched only that frozen text.\n"
          "SHA-256 is of the saved `.txt` file exactly as stored here (re-checked when this index was written).\n\n"
          "| Scenario | Run id | Source URL | Access date/time (local) | Snapshot file | SHA-256 |\n|---|---|---|---|---|---|\n")
    for csv_name, label in LABELS.items():
        r = runs[csv_name]
        meta = json.loads((snaps / f"{r['run_id']}_pricing.meta.json").read_text(encoding="utf-8"))
        actual = hashlib.sha256((snaps / f"{r['run_id']}_pricing.txt").read_bytes()).hexdigest()
        if actual != meta["sha256"]:
            sys.exit(f"hash mismatch for {r['run_id']}")
        md += f"| {label} | {r['run_id']} | {meta['url']} | {meta['accessed_at']} | `snapshots/{r['run_id']}_pricing.txt` | `{meta['sha256']}` |\n"
    md += ("\n`snapshots/<run id>_pricing.meta.json` also records the SHA-256 of the raw HTML. The measurement runs (v1 to v4) recorded their text\n"
           "hashes in `raw/part4_v*_measure_summary.json`; they were all identical to the one above when the page text did not change.\n")
    (REPORT / "part4" / "EVIDENCE.md").write_text(md, encoding="utf-8", newline="\n")
    print(md)


if __name__ == "__main__":
    main()
