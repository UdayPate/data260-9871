"""
DATA-260 Homework 10 Part 1 - data access for the Streamlit dashboard. Pure functions (no Streamlit), so they can be tested on their own.

Sources (all under reports/hw10/raw, written by the real runs):
  spans_*.jsonl             one JSON span per stage and trace_id (Part 4.1): the only source for request counts, hit/miss, errors and latency
  part2_eval_results.json   Part 2 evaluator output;   part3_judge_scores.json   Part 3 judge validation;   part4_trace_ids.json   the three required traces
"""

import json
import statistics
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw10" / "raw"


def span_files() -> list[Path]:
    return sorted(RAW.glob("spans_*.jsonl"))


def signature() -> tuple:
    """Changes whenever a spans/results file changes, so cached loads refresh."""
    return tuple((p.name, p.stat().st_mtime_ns) for p in [*span_files(), *RAW.glob("part[234]_*.json")])


def load_spans() -> list[dict]:
    out = []
    for p in span_files():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                s = json.loads(line)
                s["source"] = p.name
                out.append(s)
    return out


def load_json(name: str) -> dict:
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def requests(spans: list[dict]) -> list[dict]:
    """One row per request = the root `request` span: path hit/miss, status, end-to-end duration, start/end, source file."""
    return [{"trace_id": s["trace_id"], "path": s["attrs"].get("path"), "status": s["status"], "error": s["error"], "latency_ms": s["duration_ms"],
             "start": s["start"], "start_ms": s["start_ms"], "end": s["end"], "source": s["source"]} for s in spans if s["stage"] == "request"]


def in_window(rows: list[dict], sources: list[str], last_hours: float | None) -> tuple[list[dict], str]:
    """Filter request rows by source file and by 'the last N hours before the newest recorded request'. Returns (rows, window description)."""
    rows = [r for r in rows if r["source"] in sources]
    if not rows:
        return [], "no requests in the selected sources"
    newest = max(r["start_ms"] for r in rows)
    if last_hours is not None:
        rows = [r for r in rows if r["start_ms"] >= newest - last_hours * 3600_000]
    first, last = min(r["start"] for r in rows), max(r["end"] for r in rows)
    return rows, f"{first.replace('T', ' ')} to {last.replace('T', ' ')} (local time)"


def summary(rows: list[dict]) -> dict:
    hits = [r for r in rows if r["path"] == "hit"]
    misses = [r for r in rows if r["path"] == "miss"]
    errors = [r for r in rows if r["status"] == "error"]
    lat = lambda rs, q: percentile([r["latency_ms"] for r in rs], q)  # noqa: E731
    return {"requests": len(rows), "hits": len(hits), "misses": len(misses), "hit_rate_pct": round(100 * len(hits) / len(rows), 1) if rows else None,
            "errors": len(errors), "error_rate_pct": round(100 * len(errors) / len(rows), 1) if rows else None,
            "hit_p50": lat(hits, 50), "hit_p95": lat(hits, 95), "miss_p50": lat(misses, 50), "miss_p95": lat(misses, 95),
            "all_mean": statistics.mean(r["latency_ms"] for r in rows) if rows else None}


def trace(spans: list[dict], trace_id: str) -> list[dict]:
    """All spans of one trace in stage order (by start time, longer span first on ties so the root request comes first)."""
    return sorted((s for s in spans if s["trace_id"] == trace_id.strip()), key=lambda s: (s["start_ms"], -s["duration_ms"]))


def trace_kind(rows: list[dict]) -> str:
    cl = next((s for s in rows if s["stage"] == "cache_lookup"), None)
    failed = any(s["status"] == "error" for s in rows)
    path = cl["attrs"].get("path") if cl else None
    return ("CACHE HIT" if path == "hit" else "CACHE MISS" if path == "miss" else "UNKNOWN") + (" - FAILED" if failed else "")
