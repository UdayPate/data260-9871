"""
DATA-260 Homework 9 - Part 2: run 13 queries (new questions, exact duplicates, paraphrases) through the semantic cache in front of the REAL
HW8 pipeline (Planner, Writer, Reviewer as separate processes, qwen3:8b via Ollama, over Kafka) and report what was measured.

    code\\venv\\Scripts\\python.exe code/cache_hw9/run_part2.py [--threshold 0.85] [--out-dir DIR]

Needs: docker compose up -d kafka kafka-init redis (from the repo root), MySQL, Ollama with qwen3:8b. It resets the four pipeline topics, starts the three
agents itself and stops them at the end. One warm-up question (not counted, not cached) is sent first so that qwen3's load time is not charged to
the first real query. --fake-agent (development only, needs no Kafka or model) swaps the pipeline for a canned answer and refuses to write into raw/.
Writes part2_results.json / .csv / part2_cache.log and the agents' own logs to --out-dir (default reports/hw09/raw).
"""

import argparse
import csv
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

import redis

from qa_service import CachedQA
from semantic_cache import SemanticCache, embed

HERE = Path(__file__).resolve().parent
KAFKA_DIR = HERE.parent / "kafka_hw8"
DEFAULT_OUT = HERE.parents[1] / "reports" / "hw09" / "raw"
sys.path.insert(0, str(KAFKA_DIR))

# (kind, query, source). "duplicate" repeats the query numbered `source` exactly; "paraphrase" rewords it; "new" has no source and should MISS.
# The sources were fixed before the first run and are not changed afterwards; they decide which hits count as false hits.
QUERIES = [
    ("new", "Which team is the home team for fixture FX-9871-00005?", None),
    ("duplicate", "Which team is the home team for fixture FX-9871-00005?", 1),
    ("new", "Who is playing in fixture FX-9871-00006?", None),
    ("paraphrase", "Tell me which team hosts fixture FX-9871-00005 at home.", 1),
    ("new", "What are the basic rules of volleyball scoring?", None),
    ("duplicate", "Who is playing in fixture FX-9871-00006?", 3),
    ("paraphrase", "Which two teams are playing in fixture FX-9871-00006?", 3),
    ("new", "How many player spots are still available for fixture FX-9871-00007?", None),
    ("duplicate", "What are the basic rules of volleyball scoring?", 5),
    ("paraphrase", "How does scoring work in volleyball?", 5),
    ("duplicate", "How many player spots are still available for fixture FX-9871-00007?", 8),
    ("paraphrase", "How many open player slots are left on fixture FX-9871-00007?", 8),
    ("new", "What is the home ground of the home team for fixture FX-9871-00008?", None),
]
EXPECTED = {"new": "miss", "duplicate": "hit", "paraphrase": "hit (hoped)"}


def kill(proc):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


def start_agents(out_dir: Path):
    import failure_tests as ft  # HW8 harness: reuse its topic reset
    ft.console = open(os.devnull, "w")
    ft.TOPIC_PARTITIONS.clear()
    ft.TOPIC_PARTITIONS.update({"s9871_inbox": 1, "s9871_tasks": 2, "s9871_drafts": 1, "s9871_final": 1, "s9871_dead_letter": 1})
    ft.reset_topics()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "HW8_MODE": "fixed", "HW8_GROUP_SUFFIX": f"_hw9_{uuid.uuid4().hex[:6]}",
           "HW8_STATE_DIR": tempfile.mkdtemp(prefix="hw9_agents_")}
    procs = []
    for name in ("planner", "writer", "reviewer"):
        procs.append((name, subprocess.Popen([sys.executable, "-u", f"{name}.py"], cwd=KAFKA_DIR, env=env,
                                             stdout=open(out_dir / f"part2_agent_{name}.log", "wb"), stderr=subprocess.STDOUT)))
    end = time.time() + 90
    while time.time() < end and not all("ready and listening" in (out_dir / f"part2_agent_{n}.log").read_text(errors="replace") for n, _ in procs):
        time.sleep(0.5)
    return [p for _, p in procs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--fake-agent", action="store_true", help="development only: canned pipeline, no Kafka/model")
    args = ap.parse_args()
    if args.fake_agent and args.out_dir.resolve() == DEFAULT_OUT.resolve():
        sys.exit("--fake-agent is for development: give it a different --out-dir")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d [qa] %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.FileHandler(args.out_dir / "part2_cache.log", mode="w", encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        logging.getLogger("qa_service").addHandler(handler)
    logging.getLogger("qa_service").setLevel(logging.INFO)

    try:
        redis.Redis().ping()
    except redis.exceptions.RedisError:
        sys.exit("Redis is not reachable on localhost:6379 - run: docker compose up -d redis")
    cache = SemanticCache()
    cache.clear()
    procs, pipeline = [], None
    try:
        if args.fake_agent:
            def agent_fn(text):
                return {"status": "approved", "answer": "fake answer (development run)"}
        else:
            from pipeline_client import PipelineClient
            procs = start_agents(args.out_dir)
            pipeline = PipelineClient()
            print("warm-up (not counted): loading qwen3 through the pipeline ...", flush=True)
            warm = pipeline.ask("Warm-up question: name one team sport.")
            print(f"warm-up finished, pipeline status={warm['status']}\n", flush=True)
            agent_fn = pipeline.ask
        embed("warm-up")  # load MiniLM before the first timed query
        qa = CachedQA(cache, agent_fn, threshold=args.threshold)

        print(f"=== HW9 Part 2: semantic cache, threshold {args.threshold}, {len(QUERIES)} queries ===\n", flush=True)
        results = []
        for i, (kind, query, source) in enumerate(QUERIES, 1):
            r = qa.ask(query)
            source_query = QUERIES[source - 1][1] if source else None
            # a false hit = served from the cache although the right answer is not that entry's (a "new" question, or a different source)
            r.update(index=i, kind=kind, expected=EXPECTED[kind], source_index=source, source_query=source_query,
                     false_hit=bool(r["is_cached"] and r["matched_query"] != source_query))
            results.append(r)
            sim = "n/a" if r["similarity"] is None else f"{r['similarity']:.4f}"
            print(f"#{i:02d} [{kind:<10}] is_cached={str(r['is_cached']):<5} similarity={sim:<7} latency={r['latency_ms']:>9.1f} ms  status={r['status']}"
                  f"{'  ** FALSE HIT: matched ' + repr(r['matched_query']) if r['false_hit'] else ''}\n     {query}\n", flush=True)
    finally:
        if pipeline:
            pipeline.close()
        for p in procs:
            kill(p)

    hits = [r for r in results if r["is_cached"]]
    misses = [r for r in results if not r["is_cached"]]
    mean = lambda rs: round(sum(r["latency_ms"] for r in rs) / len(rs), 1) if rs else None  # noqa: E731
    summary = {"queries": len(results), "hits": len(hits), "misses": len(misses), "hit_rate_pct": round(100 * len(hits) / len(results), 1),
               "mean_latency_cached_ms": mean(hits), "mean_latency_not_cached_ms": mean(misses),
               "false_hits": sum(r["false_hit"] for r in results), "false_hit_indexes": [r["index"] for r in results if r["false_hit"]],
               "by_kind": {k: {"asked": sum(r["kind"] == k for r in results), "hits": sum(r["kind"] == k and r["is_cached"] for r in results)}
                           for k in ("new", "duplicate", "paraphrase")}}
    print("=== Summary ===")
    print(json.dumps(summary, indent=2))
    out = {"part": 2, "threshold": args.threshold, "embedding_model": "sentence-transformers/all-MiniLM-L6-v2", "index": "RediSearch FLAT, COSINE",
           "agent": "fake (development)" if args.fake_agent else "HW8 pipeline: Planner/Writer/Reviewer over Kafka, qwen3:8b (thinking off)",
           "warm_up_excluded": not args.fake_agent, "run_at": datetime.now().isoformat(timespec="seconds"), "SEED": 9871,
           "summary": summary, "results": results}
    (args.out_dir / "part2_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(args.out_dir / "part2_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "kind", "query", "is_cached", "similarity", "latency_ms", "embed_ms", "search_ms", "agent_ms", "status", "matched_query", "false_hit"])
        for r in results:
            t = r["timings_ms"]
            w.writerow([r["index"], r["kind"], r["query"], r["is_cached"], r["similarity"], r["latency_ms"], t["embed_ms"], t["search_ms"],
                        t.get("agent_ms", ""), r["status"], r["matched_query"] or "", r["false_hit"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
