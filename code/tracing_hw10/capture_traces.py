"""
DATA-260 Homework 10 - Part 4.1/4.2: capture the three required traces through the REAL system (semantic cache -> Kafka -> Planner/Writer/Reviewer, qwen3:8b).

    code\\venv\\Scripts\\python.exe code/tracing_hw10/capture_traces.py [--out-dir DIR]

  1. cache-miss trace   a new question: cache_lookup (miss) -> inbox -> planner -> writer -> reviewer -> final, answer cached
  2. cache-hit trace    the same question again: cache_lookup (hit) and nothing else downstream
  3. failed trace       the Writer process is replaced by one whose Ollama endpoint is unreachable (OLLAMA_HOST), so the Writer exhausts its three
                        attempts and dead-letters the message; the ingress then reports the missing answer. Nothing is faked: the failure is a real one.

Every span goes to <out-dir>/spans_traces.jsonl (HW10_SPANS); the three trace_ids go to <out-dir>/part4_trace_ids.json for the dashboard and the report.
Needs docker compose up -d kafka kafka-init redis, MySQL and Ollama with qwen3:8b. Resets the pipeline topics and the semantic cache.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "cache_hw9"), str(HERE.parent / "kafka_hw8")]
import harness  # noqa: E402
from pipeline_client import PipelineClient  # noqa: E402
from qa_service import CachedQA  # noqa: E402
from semantic_cache import SemanticCache, embed  # noqa: E402

DEFAULT_OUT = HERE.parents[1] / "reports" / "hw10" / "raw"
Q_OK = "Which team is the home team for fixture FX-9871-00012?"
Q_FAIL = "How many open player slots are left on fixture FX-9871-00031?"


def show(spans: list[dict], trace_id: str, title: str) -> None:
    print(f"\n--- {title}: trace_id={trace_id}")
    for s in sorted((x for x in spans if x["trace_id"] == trace_id), key=lambda x: x["start_ms"]):
        extra = {k: v for k, v in s["attrs"].items() if v is not None and k in ("path", "similarity", "pipeline_status", "attempts", "stored")}
        print(f"  {s['start'][11:]}  {s['end'][11:]}  {s['duration_ms']:>9.1f} ms  {s['stage']:<13} {s['status']:<5} {s['error'] or ''} {extra or ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    spans_file = out / "spans_traces.jsonl"
    spans_file.write_text("", encoding="utf-8")

    cache = SemanticCache()
    cache.clear()
    procs, env = harness.start_agents(out, "part4", {"HW10_SPANS": str(spans_file)})  # planner, writer, reviewer (host processes); resets the four topics
    pipeline = PipelineClient()
    try:
        print("warm-up (no spans): loading qwen3 through the pipeline ...", flush=True)
        print("warm-up status:", pipeline.ask("Warm-up question: name one team sport.")["status"], flush=True)
        embed("warm-up")
        spans_file.write_text("", encoding="utf-8")  # drop the warm-up's spans; the agents already have HW10_SPANS in their environment
        os.environ["HW10_SPANS"] = str(spans_file)  # the ingress process starts tracing now
        qa = CachedQA(cache, pipeline.ask)

        miss = qa.ask(Q_OK, trace_id=str(uuid.uuid4()))
        print(f"\nmiss : is_cached={miss['is_cached']} status={miss['status']} {miss['latency_ms']:.0f} ms trace={miss['trace_id']}", flush=True)
        hit = qa.ask(Q_OK, trace_id=str(uuid.uuid4()))
        print(f"hit  : is_cached={hit['is_cached']} status={hit['status']} {hit['latency_ms']:.0f} ms trace={hit['trace_id']}", flush=True)

        # Replace the Writer with one that cannot reach its model. Same consumer group and state dir, so it takes over the Writer's partitions.
        harness.kill(procs["writer"])
        bad_log = out / "part4_agent_writer_unreachable_model.log"
        procs["writer_unreachable"] = harness.spawn("writer", {**env, "OLLAMA_HOST": "http://127.0.0.1:9"}, bad_log)
        print("replacing the Writer with one whose model endpoint is unreachable; waiting for the group to rebalance ...", flush=True)
        if not harness.wait_ready(bad_log, 90):
            print("the replacement Writer never became ready", file=sys.stderr)
            return 1
        pipeline.timeout_s = 45
        failed = qa.ask(Q_FAIL, trace_id=str(uuid.uuid4()))
        print(f"failed: is_cached={failed['is_cached']} status={failed['status']} {failed['latency_ms']:.0f} ms trace={failed['trace_id']}", flush=True)
        time.sleep(1.5)
    finally:
        pipeline.close()
        for p in procs.values():
            harness.kill(p)

    spans = [json.loads(line) for line in spans_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    show(spans, miss["trace_id"], "cache MISS (successful)")
    show(spans, hit["trace_id"], "cache HIT")
    show(spans, failed["trace_id"], "FAILED")
    bad_spans = [s for s in spans if s["trace_id"] == failed["trace_id"] and s["status"] == "error"]
    ids = {"captured_at": datetime.now().isoformat(timespec="seconds"), "spans_file": spans_file.name,
           "cache_miss_success": {"trace_id": miss["trace_id"], "question": Q_OK},
           "cache_hit": {"trace_id": hit["trace_id"], "question": Q_OK},
           "failed": {"trace_id": failed["trace_id"], "question": Q_FAIL, "failing_stage": next((s["stage"] for s in bad_spans if s["stage"] != "request"), None),
                      "error": next((s["error"] for s in bad_spans if s["stage"] != "request"), None)}}
    (out / "part4_trace_ids.json").write_text(json.dumps(ids, indent=2), encoding="utf-8")
    print("\n" + json.dumps(ids, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
