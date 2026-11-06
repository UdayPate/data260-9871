"""
DATA-260 Homework 9 - Part 3.2: threshold sweep over the 40 labeled cases in cache_cases.yaml.

1. The cache is cleared and seeded with the 10 `seeds` (query + embedding + ground-truth answer built from s9871_rel + data-version marker).
2. For each threshold in 0.75 .. 0.95 every one of the 40 cases is looked up for real: embed (MiniLM) + Redis KNN search, each timed.
   A case is a HIT when the best similarity >= threshold. It is a FALSE HIT when it was labeled `miss`, or labeled `hit` but served by a
   different entry than the one named in `matches`.
3. Latency per case = the measured lookup time (embed + search). A miss would also run the HW8 pipeline; running qwen3 40 x 5 times
   was not necessary to compare thresholds, so a miss is charged the MEASURED mean pipeline time of the 5 non-cached queries of
   the real Part 2 run (facts + agent + store, from raw/part2_results.json). That substitution is written into the output.
Nothing is read from or written to the labels; the cases file is only read.
"""

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from facts import fingerprint, fixture_facts  # noqa: E402
from semantic_cache import MODEL_NAME, SemanticCache, embed, now_ms  # noqa: E402
from validate_cases import answer_from_facts, load_cases  # noqa: E402

THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]
ROOT = Path(__file__).resolve().parents[2]


def part2_miss_cost_ms(path: Path) -> dict:
    rs = json.load(open(path, encoding="utf-8"))["results"]
    miss = [r for r in rs if not r["is_cached"]]
    per = [r["timings_ms"].get("facts_ms", 0) + r["timings_ms"].get("agent_ms", 0) + r["timings_ms"].get("store_ms", 0) for r in miss]
    return {"source": str(path.relative_to(ROOT)).replace("\\", "/"), "n_misses": len(miss), "mean_pipeline_ms": round(statistics.mean(per), 1)}


def seed_cache(cache: SemanticCache, seeds: list[dict]) -> dict:
    cache.clear()
    answers = {}
    for s in seeds:
        facts = fixture_facts([s["fixture"]])
        answers[s["id"]] = answer_from_facts(facts[s["fixture"]], s["attribute"])
        cache.store(s["query"], embed(s["query"]), answers[s["id"]], fingerprint(facts), [s["fixture"]])
    return answers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "hw09" / "raw" / "part3_sweep.json"))
    ap.add_argument("--part2", default=str(ROOT / "reports" / "hw09" / "raw" / "part2_results.json"))
    args = ap.parse_args()

    data = load_cases()
    seeds, cases = data["seeds"], data["cases"]
    by_query = {s["query"]: s["id"] for s in seeds}
    cache = SemanticCache()
    answers = seed_cache(cache, seeds)
    assert cache.size() == len(seeds), cache.size()
    miss_cost = part2_miss_cost_ms(Path(args.part2))
    embed("warm up")  # model already loaded; keeps the first timed case honest

    sims = {}  # case id -> (best similarity, matched seed id), identical at every threshold (asserted)
    sweep = []
    for th in THRESHOLDS:
        rows = []
        for c in cases:
            t0 = now_ms()
            vec = embed(c["query"])
            t1 = now_ms()
            best = cache.nearest(vec)
            t2 = now_ms()
            sim, matched = best["similarity"], by_query[best["query"]]
            assert sims.setdefault(c["id"], (sim, matched)) == (sim, matched), "similarity changed between runs"
            hit = sim >= th
            wrong = hit and (c["expected"] == "miss" or matched != c["matches"])
            lookup = t2 - t0
            rows.append({"id": c["id"], "category": c["category"], "expected": c["expected"], "query": c["query"], "similarity": sim,
                         "matched_seed": matched, "hit": hit, "false_hit": wrong,
                         "missed_true_hit": (not hit) and c["expected"] == "hit", "embed_ms": round(t1 - t0, 2), "search_ms": round(t2 - t1, 2),
                         "lookup_ms": round(lookup, 2), "latency_ms": round(lookup + (0 if hit else miss_cost["mean_pipeline_ms"]), 1)})
        hits = sum(r["hit"] for r in rows)
        fh = sum(r["false_hit"] for r in rows)
        sweep.append({"threshold": th, "cases": len(rows), "hits": hits, "false_hits": fh,
                      "missed_true_hits": sum(r["missed_true_hit"] for r in rows),
                      "misses": len(rows) - hits,
                      "hit_rate_pct": round(100 * hits / len(rows), 1),
                      "false_hit_rate_of_hits_pct": round(100 * fh / hits, 1) if hits else None,
                      "false_hit_rate_of_should_miss_pct": round(100 * fh / sum(r["expected"] == "miss" for r in rows), 1),
                      "mean_lookup_ms": round(statistics.mean(r["lookup_ms"] for r in rows), 2),
                      "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows), 1),
                      "rows": rows})
        print(f"threshold {th:.2f}: hits={hits}/40 false_hits={fh} missed_true_hits={sweep[-1]['missed_true_hits']} "
              f"mean_latency={sweep[-1]['mean_latency_ms']} ms")

    out = {"part": "3.2", "run_at": datetime.now().isoformat(timespec="seconds"), "embedding_model": MODEL_NAME,
           "cases_file": "code/cache_hw9/cache_cases.yaml", "seed_answers": answers, "miss_pipeline_cost_source": miss_cost,
           "latency_note": "latency_ms = measured lookup (embed+search) for a hit; lookup + measured mean Part 2 pipeline time for a miss",
           "thresholds": sweep}
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
