"""
DATA-260 Homework 10 - Part 2: send test questions through the REAL system (semantic cache -> Kafka -> Planner/Writer/Reviewer, qwen3:8b), then evaluate each
request from the Kafka messages alone (joined on correlation_id) with the local GEval judge.

    code\\venv\\Scripts\\python.exe code/eval_hw10/run_part2.py [--out-dir DIR]

Writes part2_eval_results.json (one record per request: the original plan/draft/final messages with their Kafka metadata, the four scores, reasons,
the interpretation) and spans_part2.jsonl (cache, agent and evaluation spans) to --out-dir (default reports/hw10/raw).
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
sys.path[:0] = [str(HERE), str(HERE.parent / "cache_hw9"), str(HERE.parent / "tracing_hw10"), str(HERE.parent / "kafka_hw8")]
import evaluator  # noqa: E402
import harness  # noqa: E402
import judge as jd  # noqa: E402
from pipeline_client import PipelineClient  # noqa: E402
from qa_service import CachedQA  # noqa: E402
from semantic_cache import SemanticCache, embed  # noqa: E402

DEFAULT_OUT = HERE.parents[1] / "reports" / "hw10" / "raw"
QUESTIONS = [  # deliberately unlike each other: HW9 showed that near-identical templates are served from the semantic cache, and a cache hit has no agent messages to evaluate
    "Which team is the home team for fixture FX-9871-00012?",
    "What should a league office check before scheduling a Soccer fixture on a shared field?",
    "How should a league office handle a team that cannot field enough players on match day?",
    "Explain how a round-robin schedule works for a six-team volleyball league.",
    "What information belongs in a fixture cancellation notice sent to both teams?",
    "Why might a league cap the number of substitutions in a cricket match?",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    spans_file = out / "spans_part2.jsonl"
    spans_file.write_text("", encoding="utf-8")

    cache = SemanticCache()
    cache.clear()
    procs, _ = harness.start_agents(out, "part2", {"HW10_SPANS": str(spans_file)})
    pipeline = PipelineClient()
    traces = []
    try:
        print("warm-up (no spans) ...", flush=True)
        pipeline.ask("Warm-up question: name one team sport.")
        embed("warm-up")
        spans_file.write_text("", encoding="utf-8")
        os.environ["HW10_SPANS"] = str(spans_file)
        qa = CachedQA(cache, pipeline.ask)
        for i, q in enumerate(QUESTIONS, 1):
            r = qa.ask(q, trace_id=str(uuid.uuid4()))
            traces.append(r["trace_id"])
            print(f"#{i} cached={r['is_cached']} status={r['status']} {r['latency_ms']:.0f} ms trace={r['trace_id']}\n   {q}", flush=True)
    finally:
        pipeline.close()
        for p in procs.values():
            harness.kill(p)

    print("\ncollecting plan/draft/final messages from Kafka and joining on correlation_id ...", flush=True)
    bundles, stats = evaluator.collect(set(traces), timeout_s=60)
    print("collect stats:", stats, flush=True)
    judge = jd.LocalJudge()
    records = []
    for i, t in enumerate(traces, 1):
        rec = evaluator.evaluate(t, bundles[t], judge)
        rec["question_no"] = i
        records.append(rec)
        sc = rec.get("scores")
        line = f"#{i} {rec['status']}" if not sc else (f"#{i} plan={sc['plan_quality']['score']} writer={sc['writer_helpfulness']['score']} "
                                                       f"final={sc['final_helpfulness']['score']} diff={sc['final_vs_draft']['difference']:+d} "
                                                       f"identical={sc['final_vs_draft']['final_equals_draft']} judge={rec['judge_ms']:.0f} ms")
        print(line, flush=True)
    doc = {"part": 2, "run_at": datetime.now().isoformat(timespec="seconds"), "judge": {"model": jd.JUDGE_MODEL, "temperature": jd.JUDGE_TEMPERATURE,
           "seed": jd.JUDGE_SEED, "thinking": False, "timeout_s_per_call": jd.JUDGE_TIMEOUT_S, "scale": jd.SCALE, "framework": "DeepEval GEval with a 5-band rubric"},
           "collect": stats, "records": records}
    (out / "part2_eval_results.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out / 'part2_eval_results.json'} ({len(records)} records) at {time.strftime('%H:%M:%S')}")
    return 0 if all(r["status"] == "ok" for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
