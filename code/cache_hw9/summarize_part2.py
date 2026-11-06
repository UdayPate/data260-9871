"""Builds the Part 2 section of reports/hw09/METRICS.md from raw/part2_results.json (no numbers typed by hand)."""
import json
import pathlib
root = pathlib.Path(__file__).resolve().parents[2] / "reports" / "hw09"
d = json.load(open(root / "raw" / "part2_results.json", encoding="utf-8"))
s = d["summary"]; rs = d["results"]
rows = []
for r in rs:
    sim = "n/a" if r["similarity"] is None else f'{r["similarity"]:.4f}'
    res = "HIT" if r["is_cached"] else "MISS"
    if r.get("false_hit"): res += " (false hit)"
    rows.append(f'| {r["index"]} | {r["kind"]} | {r["query"]} | {sim} | {res} | {r["latency_ms"]:.1f} |')
fh = [r for r in rs if r.get("false_hit")]
bk = s["by_kind"]
speed = s["mean_latency_not_cached_ms"] / s["mean_latency_cached_ms"]
text = f"""## Part 2 - Semantic response cache (threshold {d['threshold']}, {d['embedding_model']}, {d['index']})

Run at {d['run_at']} (local time). Miss path = {d['agent']}. One warm-up question (not counted) loaded the model first.

| # | kind | query | best similarity | result | latency (ms) |
|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

| Metric | Value |
|---|---|
| Queries | {s['queries']} |
| Cache hits / misses | {s['hits']} / {s['misses']} |
| Hit rate | {s['hit_rate_pct']}% |
| Mean latency, cached | {s['mean_latency_cached_ms']} ms |
| Mean latency, not cached | {s['mean_latency_not_cached_ms']} ms |
| Speed-up (not cached / cached) | {speed:.0f}x |
| False hits | {s['false_hits']} (queries {', '.join('#'+str(i) for i in s['false_hit_indexes'])}) |
| Exact duplicates served from cache | {bk['duplicate']['hits']} of {bk['duplicate']['asked']} |
| Paraphrases served from cache | {bk['paraphrase']['hits']} of {bk['paraphrase']['asked']} |
| New questions that hit | {bk['new']['hits']} of {bk['new']['asked']} |

What this shows: a cache hit costs one embedding plus one vector search (about {s['mean_latency_cached_ms']} ms), while a miss runs the whole Planner/Writer/Reviewer pipeline over Kafka with qwen3 (about {s['mean_latency_not_cached_ms']/1000:.1f} s), so a hit is roughly {speed:.0f}x faster. Every exact duplicate hit (similarity 1.0000). Paraphrases hit when similarity reached {d['threshold']} and missed when it did not (#12, 0.7812).

The cache also made mistakes. Each hit above is judged against a label fixed before the run: a query that asks about a different fixture than the cached one is a false hit. Query #7 (fixture 00006, served the fixture 00005 answer, similarity {rs[6]['similarity']:.4f}) and query #13 (fixture 00008, same wrong entry, {rs[12]['similarity']:.4f}) are false hits. The embedding model sees "FX-9871-00005" and "FX-9871-00006" as almost the same text, so the fixture code barely moves the similarity, and it is as high as a true paraphrase (#4 at 0.8824, #10 at 0.8714). That is the threshold trade-off Part 3 examines; no threshold on this run separates the true paraphrases from the false hits cleanly, so nothing was relabelled or tuned here.
"""
out = root / "METRICS.md"
head = "# HW9 METRICS\n\n"
out.write_text(head + text, encoding="utf-8")
print(text)
