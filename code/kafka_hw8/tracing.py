"""
DATA-260 Homework 10 Part 4.1 - one structured JSON span per stage, keyed by trace_id (= the HW8 correlation_id, never a second id).

emit() appends one JSON line to the file named by the HW10_SPANS environment variable and does nothing when that variable is unset, so the
HW8 and HW9 code behaves exactly as before unless a run asks for tracing. One short write per span with O_APPEND, so the agent processes
and the ingress process can share the file without interleaving lines.

Span fields: trace_id, stage, start, end (local ISO time, ms), start_ms, end_ms (epoch ms), duration_ms, status ("ok" | "error"),
error (null unless status is "error"), attrs (stage-specific extras such as cache hit/miss or the Kafka partition/offset).
"""

import json
import os
import time
from datetime import datetime


def now_ms() -> float:
    return time.time() * 1000


def iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000).isoformat(timespec="milliseconds")


def emit(trace_id: str | None, stage: str, start_ms: float, end_ms: float, status: str = "ok", error: str | None = None, **attrs) -> dict | None:
    path = os.environ.get("HW10_SPANS")
    if not path or not trace_id:
        return None
    span = {"trace_id": trace_id, "stage": stage, "start": iso(start_ms), "end": iso(end_ms), "start_ms": round(start_ms, 1),
            "end_ms": round(end_ms, 1), "duration_ms": round(end_ms - start_ms, 1), "status": status, "error": error, "attrs": attrs}
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(span, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return span


def kafka_ms(msg) -> float | None:
    """The producer's timestamp on a consumed Kafka message (epoch ms), or None when the broker did not record one."""
    kind, ms = msg.timestamp()
    return float(ms) if kind != 0 and ms > 0 else None
