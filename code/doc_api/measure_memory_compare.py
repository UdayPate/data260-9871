"""
DATA-260 Homework 6 - Part 4.6: measurements behind the MongoDB-vs-file memory comparison.
(1) Prompt cost as memory grows: tokens needed to inject ALL of MEMORY.md (file memory loads the whole file
    every turn) vs the fixed top-3 episodic retrieval used by the MongoDB memory.
(2) Retrieval time as the number of stored items grows (file: read+parse whole file; Mongo: cosine top-3
    over a user's episodes), on synthetic items in a throwaway user.
(3) Persistence: checked separately by restarting the server (see RUN_LOG).
Usage: python measure_memory_compare.py
"""

import json
import statistics as st
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pymongo import MongoClient

import config
import embeddings
import file_memory as fm
import tokens

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw"
USER = "p4_scale_test"
TOPICS = ["league fees", "referee schedule", "jersey colours", "parking rules", "snack rota", "field bookings",
          "coach contacts", "equipment storage", "weather policy", "tournament dates", "injury protocol", "awards night"]


def synthetic_fact(i: int) -> str:
    return f"[2026-10-01] Note {i}: the {TOPICS[i % len(TOPICS)]} arrangement for group {i // 12} was agreed with the committee."


def main() -> None:
    out = {"generated": datetime.now().isoformat(timespec="seconds")}
    # ---- (1) tokens injected per turn
    ep_tokens = st.fmean(tokens.count(f"- {synthetic_fact(i)}") for i in range(3)) * 3
    rows = []
    for n in (10, 40, 100, 400, 1000):
        text = "<!-- last-consolidated: 2026-10-15T09:00:00-07:00 -->\n# Project memory\n" + "\n".join(f"- {synthetic_fact(i)}" for i in range(n)) + "\n"
        rows.append({"stored_items": n, "file_memory_tokens_per_turn": tokens.count(fm.build_system_prompt("", text)),
                     "mongo_top3_episode_tokens_per_turn": round(ep_tokens)})
    out["prompt_tokens"] = rows
    print("(1) tokens injected into EVERY prompt")
    print(f"{'stored items':>13s} {'file memory (whole file)':>26s} {'Mongo top-3 episodes':>22s}")
    for r in rows:
        print(f"{r['stored_items']:13d} {r['file_memory_tokens_per_turn']:26d} {r['mongo_top3_episode_tokens_per_turn']:22d}")

    # ---- (2) retrieval time
    col = MongoClient(config.MONGO_URI, tz_aware=True)[config.MONGO_DB]["episodes"]
    col.delete_many({"user_id": USER})
    query_vec = embeddings.embed("Who handles the referee schedule?")
    pool = [embeddings.embed(synthetic_fact(i)) for i in range(48)]       # reuse 48 real embeddings, rotate them
    timing, inserted = [], 0
    for n in (100, 1000, 10000):
        batch = [{"user_id": USER, "session_id": "s", "fact": synthetic_fact(i), "importance": 0.5,
                  "embedding": pool[i % 48], "created_at": datetime.now(timezone.utc)} for i in range(inserted, n)]
        if batch:
            col.insert_many(batch)
        inserted = n
        mongo_ms, file_ms = [], []
        with tempfile.TemporaryDirectory() as d:
            mp = Path(d) / "MEMORY.md"
            mp.write_text("<!-- last-consolidated: 2026-10-15T09:00:00-07:00 -->\n" + "\n".join(f"- {synthetic_fact(i)}" for i in range(n)) + "\n", encoding="utf-8")
            for _ in range(5):
                t0 = time.perf_counter()
                cands = list(col.find({"user_id": USER}))
                embeddings.cosine_top_k(query_vec, cands, 3)
                mongo_ms.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                fm.build_system_prompt("", fm.load_memory(str(mp)))
                fm.split_sections(fm.load_memory(str(mp)))
                file_ms.append((time.perf_counter() - t0) * 1000)
        timing.append({"stored_items": n, "mongo_retrieval_ms_median": round(st.median(mongo_ms), 1),
                       "file_load_parse_ms_median": round(st.median(file_ms), 2)})
    col.delete_many({"user_id": USER})
    out["retrieval_time"] = timing
    print("\n(2) time to fetch memory for one turn (median of 5; Mongo = load user's episodes + cosine top-3)")
    for t in timing:
        print(f"  {t['stored_items']:6d} items: Mongo {t['mongo_retrieval_ms_median']:8.1f} ms | file load+parse {t['file_load_parse_ms_median']:6.2f} ms")
    (RAW / "part4_comparison_measurements.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
