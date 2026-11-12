"""
DATA-260 Homework 10 - Part 4.3: stage-latency experiment on 50 CONFIRMED cache-miss requests through the real system (semantic cache -> Kafka -> Planner ->
Writer -> Reviewer, qwen3:8b), then the evaluator on those 50, then 10 repeated questions as cache hits (a separate metric).

    code\\venv\\Scripts\\python.exe code/tracing_hw10/run_latency.py

A request counts only if the response says is_cached=False AND its cache_lookup span says path=miss; a question the cache answers is logged and replaced by the next
one in latency_questions.POOL. Requests run one at a time (no queueing from other requests). Evaluation runs afterwards in its own pass so the judge does not share
the GPU with the pipeline being timed. Writes raw/spans_latency.jsonl, raw/part4_latency_requests.json and the console log.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "eval_hw10"), str(HERE.parent / "cache_hw9"), str(HERE.parent / "kafka_hw8")]
import evaluator  # noqa: E402
import harness  # noqa: E402
import judge as jd  # noqa: E402
from latency_questions import POOL  # noqa: E402
from pipeline_client import PipelineClient  # noqa: E402
from qa_service import CachedQA  # noqa: E402
from semantic_cache import SemanticCache, embed  # noqa: E402

OUT = HERE.parents[1] / "reports" / "hw10" / "raw"
TARGET_MISSES, HIT_REPEATS = 50, 10


def main() -> int:
    spans_file = OUT / "spans_latency.jsonl"
    spans_file.write_text("", encoding="utf-8")
    cache = SemanticCache()
    cache.clear()
    procs, _ = harness.start_agents(OUT, "part4_latency", {"HW10_SPANS": str(spans_file)})
    pipeline = PipelineClient()
    pipeline.timeout_s = 180
    misses, skipped, hits = [], [], []
    try:
        print("warm-up (no spans) ...", flush=True)
        pipeline.ask("Warm-up question: name one team sport.")
        embed("warm-up")
        spans_file.write_text("", encoding="utf-8")
        os.environ["HW10_SPANS"] = str(spans_file)
        qa = CachedQA(cache, pipeline.ask)
        for q in POOL:
            if len(misses) == TARGET_MISSES:
                break
            r = qa.ask(q, trace_id=str(uuid.uuid4()))
            if r["is_cached"]:
                skipped.append({"question": q, "trace_id": r["trace_id"], "similarity": r["similarity"], "matched_query": r["matched_query"]})
                print(f"SKIPPED (served from cache, similarity {r['similarity']:.4f}): {q}", flush=True)
                continue
            misses.append({"n": len(misses) + 1, "question": q, "trace_id": r["trace_id"], "status": r["status"], "latency_ms": r["latency_ms"],
                           "similarity": r["similarity"]})
            print(f"miss {len(misses):02d}/{TARGET_MISSES} status={r['status']:<9} {r['latency_ms']:>7.0f} ms  best_similarity={r['similarity'] if r['similarity'] is None else round(r['similarity'], 3)}  {q[:60]}", flush=True)
        if len(misses) < TARGET_MISSES:
            print(f"only {len(misses)} confirmed misses: question pool exhausted", file=sys.stderr)
            return 1
        stored = [m for m in misses if m["status"] == "approved"][:HIT_REPEATS]
        for m in stored:  # exact repeats of answered questions: the cache-hit path, kept separate from the 50 misses
            r = qa.ask(m["question"], trace_id=str(uuid.uuid4()))
            hits.append({"question": m["question"], "trace_id": r["trace_id"], "is_cached": r["is_cached"], "latency_ms": r["latency_ms"], "similarity": r["similarity"]})
        print(f"\n{len(hits)} repeats: {sum(h['is_cached'] for h in hits)} served from cache, mean {sum(h['latency_ms'] for h in hits) / len(hits):.1f} ms", flush=True)
    finally:
        pipeline.close()
        for p in procs.values():
            harness.kill(p)

    spans = [json.loads(line) for line in spans_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    path_of = {s["trace_id"]: s["attrs"]["path"] for s in spans if s["stage"] == "cache_lookup"}
    confirmed = [m for m in misses if path_of.get(m["trace_id"]) == "miss"]
    print(f"\nconfirmed misses (response and cache_lookup span agree): {len(confirmed)} of {len(misses)}")
    if len(confirmed) != len(misses):
        return 1

    print("\nevaluating the 50 requests (judge runs after the pipeline, so it does not share the GPU with it) ...", flush=True)
    bundles, stats = evaluator.collect({m["trace_id"] for m in misses}, timeout_s=90)
    print("collect:", stats, flush=True)
    judge, ev_status = jd.LocalJudge(), {}
    for m in misses:
        rec = evaluator.evaluate(m["trace_id"], bundles[m["trace_id"]], judge)
        ev_status[m["trace_id"]] = rec["status"]
        m["evaluation_status"] = rec["status"]
        if rec["status"] == "ok":
            m["evaluation_scores"] = {k: v["score"] for k, v in rec["scores"].items() if k != "final_vs_draft"}
            m["final_minus_draft"] = rec["scores"]["final_vs_draft"]["difference"]
        print(f"eval {m['n']:02d} {rec['status']}", flush=True)
    doc = {"run_at": datetime.now().isoformat(timespec="seconds"), "target_misses": TARGET_MISSES, "confirmed_misses": len(confirmed), "skipped_cache_served": skipped,
           "collect": stats, "misses": misses, "hit_repeats": hits}
    (OUT / "part4_latency_requests.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote part4_latency_requests.json")
    return 0 if all(v == "ok" for v in ev_status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
