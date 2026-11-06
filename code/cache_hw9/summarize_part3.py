"""Builds the Part 3 section of reports/hw09/METRICS.md (3.2 - 3.5) from raw/part3_*.json. No number is typed by hand."""

import argparse
import json
from pathlib import Path

from cost_model import C_FALSE, C_MISS, cheapest, total_cost

ROOT = Path(__file__).resolve().parents[2]
CATS = ["exact_duplicate", "paraphrase", "different_answer", "unrelated"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "reports/hw09/raw"))
    ap.add_argument("--metrics", default=str(ROOT / "reports/hw09/METRICS.md"))
    a = ap.parse_args()
    raw = Path(a.raw)
    sw = json.load(open(raw / "part3_sweep.json", encoding="utf-8"))
    fh = json.load(open(raw / "part3_false_hit.json", encoding="utf-8"))
    st = json.load(open(raw / "part3_stale_results.json", encoding="utf-8"))
    ths = sw["thresholds"]
    for t in ths:
        t["total_cost"] = total_cost(t)
    best = cheapest(ths, C_FALSE)
    # the prose below states these findings; fail loudly if a future run's numbers no longer support them
    diff_min = min(r["similarity"] for r in ths[0]["rows"] if r["category"] == "different_answer")
    para_max = max(r["similarity"] for r in ths[0]["rows"] if r["category"] == "paraphrase")
    assert diff_min > para_max, "prose assumes different-answer cases score above every paraphrase"
    assert best is ths[-1], "prose assumes the highest threshold is cheapest"
    assert ths[-1]["false_hits"] > 0, "prose assumes false hits remain at the top threshold"
    (raw / "part3_costs.json").write_text(json.dumps(
        {"C_MISS_usd": C_MISS, "C_FALSE_usd": C_FALSE, "formula": "misses*C_MISS + false_hits*C_FALSE over the 40 cases",
         "per_threshold": [{"threshold": t["threshold"], "misses": t["misses"], "false_hits": t["false_hits"], "total_cost_usd": t["total_cost"]} for t in ths],
         "cheapest_threshold": best["threshold"]}, indent=2), encoding="utf-8")

    def by_cat(t):
        rows = t["rows"]
        return {c: (sum(r["hit"] for r in rows if r["category"] == c), sum(r["false_hit"] for r in rows if r["category"] == c)) for c in CATS}

    table = ["| Threshold | Hit rate | False-hit rate (false hits / hits) | Mean latency (ms) | Total cost (USD) |", "|---|---|---|---|---|"]
    for t in ths:
        fr = "n/a" if t["false_hit_rate_of_hits_pct"] is None else f'{t["false_hit_rate_of_hits_pct"]}% ({t["false_hits"]}/{t["hits"]})'
        table.append(f'| {t["threshold"]:.2f} | {t["hit_rate_pct"]}% ({t["hits"]}/40) | {fr} | {t["mean_latency_ms"]} | {t["total_cost"]:.2f} |')
    cat_tbl = ["| Threshold | exact duplicates hit | paraphrases hit | different-answer hit (all false) | unrelated hit (all false) | true hits wrongly missed | misses |", "|---|---|---|---|---|---|---|"]
    for t in ths:
        b = by_cat(t)
        cat_tbl.append(f'| {t["threshold"]:.2f} | {b["exact_duplicate"][0]}/10 | {b["paraphrase"][0]}/10 | {b["different_answer"][0]}/10 | {b["unrelated"][0]}/10 | {t["missed_true_hits"]} | {t["misses"]} |')
    rows85 = next(t for t in ths if t["threshold"] == 0.85)["rows"]
    t95 = next(t for t in ths if t["threshold"] == 0.95)
    sims = {c: sorted(r["similarity"] for r in rows85 if r["category"] == c) for c in CATS}
    rng = {c: f"{v[0]:.4f} - {v[-1]:.4f}" for c, v in sims.items()}
    n_lat = sw["miss_pipeline_cost_source"]
    sens = ["| C_FALSE (USD) | cheapest threshold | its total (USD) |", "|---|---|---|"]
    for cf in (0.01, 0.05, 0.25, 2.5, 25):
        b = cheapest(ths, cf)
        sens.append(f'| {cf} | {b["threshold"]:.2f} | {total_cost(b, C_MISS, cf):.2f} |')
    d = st["steps"]
    lat = d["8_hit_latency_ms"]

    text = f"""
## Part 3 - Threshold economics and stale answers

### 3.1 / 3.2 Labeled set and threshold sweep

The 40 labels in `code/cache_hw9/cache_cases.yaml` were committed (commit 1c72c91) before any threshold was run; they were not edited afterwards.
The cache held the 10 seed queries. Run at {sw['run_at']} (local time). A *false hit* is a case labeled "miss" that was served from the
cache, or a "hit" case served by the wrong entry. False-hit rate = false hits / hits (the share of cached answers that are wrong).
Latency = measured lookup (embedding + Redis search) for a hit; for a miss, lookup plus the measured mean pipeline time of the {n_lat['n_misses']}
non-cached queries of the real Part 2 run ({n_lat['mean_pipeline_ms']} ms, `{n_lat['source']}`) - the pipeline itself was not re-run 200 times.

""" + "\n".join(table) + """

Where the hits come from (same run):

""" + "\n".join(cat_tbl) + f"""

Best similarity per category at every threshold (it does not depend on the threshold): exact duplicates {rng['exact_duplicate']}; paraphrases
{rng['paraphrase']}; different-answer {rng['different_answer']}; unrelated {rng['unrelated']}.

What this shows: the different-answer questions are *more* similar to the cached entry than the true paraphrases are, so raising the threshold removes
true hits ({ths[0]['missed_true_hits']} lost at 0.75, {t95['missed_true_hits']} at 0.95) while the false hits barely move ({ths[0]['false_hits']} at 0.75, {t95['false_hits']} at 0.95).
At 0.95, {by_cat(t95)['different_answer'][0]} of the 10 different-answer questions are still served a wrong cached answer. No threshold in this range separates the two groups.
The false hits beyond the different-answer ones (at 0.75: {ths[0]['false_hits'] - by_cat(ths[0])['different_answer'][0]}) are paraphrases that were served by the wrong cached entry (a lower threshold lets a nearer-but-wrong seed win).

### 3.3 One false hit in full ({fh['case_id']}, chosen by the rule: highest-similarity different-answer hit at 0.85)

- Cached query: `{fh['cached_query']}`
- Incoming query: `{fh['incoming_query']}`
- Similarity: **{fh['similarity']}** (threshold 0.85, so it was served from the cache)
- Cached answer returned: {fh['cached_answer_returned']}
- Correct answer (read from s9871_rel): {fh['correct_answer']}
- Why the model confuses them: the two sentences have {fh['n_tokens']} word-pieces each and differ only in {len(fh['differing_token_pairs'])} of them: {', '.join(f"`{x}` vs `{y}`" for x, y in fh['differing_token_pairs'])}.
  all-MiniLM-L6-v2 encodes the meaning of the sentence (a question about the home ground of a fixture); the fixture code is just a few digit
  pieces the model has no reason to treat as the part that decides the answer. For scale, a genuine paraphrase pair ({fh['true_paraphrase_for_scale']['case']}: "{fh['true_paraphrase_for_scale']['query']}"
  vs the cached "{fh['true_paraphrase_for_scale']['vs']}") scores only {fh['true_paraphrase_for_scale']['similarity']}, lower than this false hit.

### 3.4 Cost model and threshold choice

Total cost over the 40 cases = (cases not served from cache) x C_MISS + (false hits) x C_FALSE, with C_MISS = {C_MISS} USD and C_FALSE = {C_FALSE} USD.
- C_MISS = {C_MISS} USD: a miss runs the HW8 pipeline (three qwen3 calls plus Kafka and a database lookup, about {n_lat['mean_pipeline_ms']/1000:.1f} s of GPU time here);
  priced at an API-equivalent ~0.003 USD per model call, three calls come to about 0.01 USD. A hit costs about nothing, so this is what a hit saves.
- C_FALSE = {C_FALSE} USD: a false hit gives the user a confident wrong fixture fact; the cost is one support contact, about 5 minutes of league-staff time
  at 30 USD/hour. It ignores the cost of a player turning up at the wrong ground, so it is on the low side.
Both are assumptions (`code/cache_hw9/cost_model.py`), so the cheapest threshold is also computed for other values of C_FALSE:

""" + "\n".join(sens) + f"""

**Threshold to ship: {best['threshold']:.2f}** (total {best['total_cost']:.2f} USD, the lowest in the sweep). A false hit is {C_FALSE/C_MISS:.0f}x as costly as a miss, so the
cheapest choice is the highest threshold: it loses {best['missed_true_hits']} true hits but avoids the most wrong answers. It is not a good result in absolute terms:
{best['false_hits']} false hits remain at {best['threshold']:.2f}, because the embedding cannot tell one fixture code from another. Raising the threshold is the wrong tool for that
failure; it needs a structural guard (for example, only serve a hit if the fixture codes in both queries are identical), which was not implemented because the assignment asks only to choose a threshold.

### 3.5 Stale answers and invalidation

Cached query: `{st['query']}` - depends on `fixtures.spots_available` of the single row {st['fixture']}. The row was changed from {st['old_spots']} to {st['new_spots']} and restored to {st['restored_spots']} at the end.

| Step | Result |
|---|---|
""" + "\n".join(f"| {c['check']} | {'PASS' if c['pass'] else 'FAIL'} - {c['detail']} |" for c in st["checks"]) + f"""

Strategy: version check on hit. Each entry stores a data-version marker (a SHA-256 fingerprint of the fixture fields the answer was built from). On a hit,
the handler recomputes the fingerprint of the entry's rows from MySQL; if it differs, the entry is deleted and the question goes through the pipeline again
(step 6: version {d['1_miss']['data_version']} -> {d['6_invalidated']['data_version']}). The marker is a content fingerprint, not `updated_at`,
because `updated_at` also changes on every Part 1 view-counter sync (control 3a: it changed and the entry was correctly kept).

Trade-off: it never serves a stale answer for the fields it fingerprints, and it does not invalidate on unrelated edits, but every hit now pays a database read and the
cache depends on MySQL being reachable: mean hit latency was {lat['without_check']['mean']} ms without the check and {lat['with_check']['mean']} ms with it ({lat['with_check']['n']} hits each),
and a hit still cannot be served from Redis alone. A TTL would be cheaper per hit but would leave a window in which stale answers are served.
"""
    p = Path(a.metrics)
    cur = p.read_text(encoding="utf-8") if p.exists() else "# HW9 METRICS\n"
    cur = cur.split("\n## Part 3 - ")[0].rstrip() + "\n"
    p.write_text(cur + text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
