# HW9 METRICS

## Part 2 - Semantic response cache (threshold 0.85, sentence-transformers/all-MiniLM-L6-v2, RediSearch FLAT, COSINE)

Run at 2026-11-06T15:20:39 (local time). Miss path = HW8 pipeline: Planner/Writer/Reviewer over Kafka, qwen3:8b (thinking off). One warm-up question (not counted) loaded the model first.

| # | kind | query | best similarity | result | latency (ms) |
|---|---|---|---|---|---|
| 1 | new | Which team is the home team for fixture FX-9871-00005? | n/a | MISS | 5192.0 |
| 2 | duplicate | Which team is the home team for fixture FX-9871-00005? | 1.0000 | HIT | 18.2 |
| 3 | new | Who is playing in fixture FX-9871-00006? | 0.8051 | MISS | 5314.4 |
| 4 | paraphrase | Tell me which team hosts fixture FX-9871-00005 at home. | 0.8824 | HIT | 14.8 |
| 5 | new | What are the basic rules of volleyball scoring? | 0.1825 | MISS | 6800.9 |
| 6 | duplicate | Who is playing in fixture FX-9871-00006? | 1.0000 | HIT | 13.8 |
| 7 | paraphrase | Which two teams are playing in fixture FX-9871-00006? | 0.8872 | HIT (false hit) | 11.7 |
| 8 | new | How many player spots are still available for fixture FX-9871-00007? | 0.6700 | MISS | 4577.2 |
| 9 | duplicate | What are the basic rules of volleyball scoring? | 1.0000 | HIT | 13.3 |
| 10 | paraphrase | How does scoring work in volleyball? | 0.8714 | HIT | 10.5 |
| 11 | duplicate | How many player spots are still available for fixture FX-9871-00007? | 1.0000 | HIT | 11.9 |
| 12 | paraphrase | How many open player slots are left on fixture FX-9871-00007? | 0.7812 | MISS | 4558.4 |
| 13 | new | What is the home ground of the home team for fixture FX-9871-00008? | 0.8708 | HIT (false hit) | 14.8 |

| Metric | Value |
|---|---|
| Queries | 13 |
| Cache hits / misses | 8 / 5 |
| Hit rate | 61.5% |
| Mean latency, cached | 13.6 ms |
| Mean latency, not cached | 5288.6 ms |
| Speed-up (not cached / cached) | 389x |
| False hits | 2 (queries #7, #13) |
| Exact duplicates served from cache | 4 of 4 |
| Paraphrases served from cache | 3 of 4 |
| New questions that hit | 1 of 5 |

What this shows: a cache hit costs one embedding plus one vector search (about 13.6 ms), while a miss runs the whole Planner/Writer/Reviewer pipeline over Kafka with qwen3 (about 5.3 s), so a hit is roughly 389x faster. Every exact duplicate hit (similarity 1.0000). Paraphrases hit when similarity reached 0.85 and missed when it did not (#12, 0.7812).

The cache also made mistakes. Each hit above is judged against a label fixed before the run: a query that asks about a different fixture than the cached one is a false hit. Query #7 (fixture 00006, served the fixture 00005 answer, similarity 0.8872) and query #13 (fixture 00008, same wrong entry, 0.8708) are false hits. The embedding model sees "FX-9871-00005" and "FX-9871-00006" as almost the same text, so the fixture code barely moves the similarity, and it is as high as a true paraphrase (#4 at 0.8824, #10 at 0.8714). That is the threshold trade-off Part 3 examines; no threshold on this run separates the true paraphrases from the false hits cleanly, so nothing was relabelled or tuned here.

## Part 3 - Threshold economics and stale answers

### 3.1 / 3.2 Labeled set and threshold sweep

The 40 labels in `code/cache_hw9/cache_cases.yaml` were committed (commit 1c72c91) before any threshold was run; they were not edited afterwards.
The cache held the 10 seed queries. Run at 2026-11-06T15:49:43 (local time). A *false hit* is a case labeled "miss" that was served from the
cache, or a "hit" case served by the wrong entry. False-hit rate = false hits / hits (the share of cached answers that are wrong).
Latency = measured lookup (embedding + Redis search) for a hit; for a miss, lookup plus the measured mean pipeline time of the 5
non-cached queries of the real Part 2 run (5275.1 ms, `reports/hw09/raw/part2_results.json`) - the pipeline itself was not re-run 200 times.

| Threshold | Hit rate | False-hit rate (false hits / hits) | Mean latency (ms) | Total cost (USD) |
|---|---|---|---|---|
| 0.75 | 75.0% (30/40) | 50.0% (15/30) | 1326.9 | 37.60 |
| 0.80 | 70.0% (28/40) | 50.0% (14/28) | 1592.4 | 35.12 |
| 0.85 | 65.0% (26/40) | 46.2% (12/26) | 1854.2 | 30.14 |
| 0.90 | 60.0% (24/40) | 45.8% (11/24) | 2117.8 | 27.66 |
| 0.95 | 55.0% (22/40) | 45.5% (10/22) | 2382.4 | 25.18 |

Where the hits come from (same run):

| Threshold | exact duplicates hit | paraphrases hit | different-answer hit (all false) | unrelated hit (all false) | true hits wrongly missed | misses |
|---|---|---|---|---|---|---|
| 0.75 | 10/10 | 10/10 | 10/10 | 0/10 | 0 | 10 |
| 0.80 | 10/10 | 8/10 | 10/10 | 0/10 | 2 | 12 |
| 0.85 | 10/10 | 6/10 | 10/10 | 0/10 | 4 | 14 |
| 0.90 | 10/10 | 4/10 | 10/10 | 0/10 | 6 | 16 |
| 0.95 | 10/10 | 2/10 | 10/10 | 0/10 | 8 | 18 |

Best similarity per category at every threshold (it does not depend on the threshold): exact duplicates 1.0000 - 1.0000; paraphrases
0.7745 - 0.9751; different-answer 0.9958 - 0.9990; unrelated -0.0053 - 0.4148.

What this shows: the different-answer questions are *more* similar to the cached entry than the true paraphrases are, so raising the threshold removes
true hits (0 lost at 0.75, 8 at 0.95) while the false hits barely move (15 at 0.75, 10 at 0.95).
At 0.95, 10 of the 10 different-answer questions are still served a wrong cached answer. No threshold in this range separates the two groups.
The false hits beyond the different-answer ones (at 0.75: 5) are paraphrases that were served by the wrong cached entry (a lower threshold lets a nearer-but-wrong seed win).

### 3.3 One false hit in full (C23, chosen by the rule: highest-similarity different-answer hit at 0.85)

- Cached query: `What is the home ground for fixture FX-9871-00007?`
- Incoming query: `What is the home ground for fixture FX-9871-00008?`
- Similarity: **0.999** (threshold 0.85, so it was served from the cache)
- Cached answer returned: The home ground is Cardoza Park, Milpitas.
- Correct answer (read from s9871_rel): The home ground is Backesto Park, San Jose.
- Why the model confuses them: the two sentences have 17 word-pieces each and differ only in 1 of them: `##7` vs `##8`.
  all-MiniLM-L6-v2 encodes the meaning of the sentence (a question about the home ground of a fixture); the fixture code is just a few digit
  pieces the model has no reason to treat as the part that decides the answer. For scale, a genuine paraphrase pair (C14: "What is fixture FX-9871-00008 called?"
  vs the cached "What is the name of fixture FX-9871-00008?") scores only 0.9626, lower than this false hit.

### 3.4 Cost model and threshold choice

Total cost over the 40 cases = (cases not served from cache) x C_MISS + (false hits) x C_FALSE, with C_MISS = 0.01 USD and C_FALSE = 2.5 USD.
- C_MISS = 0.01 USD: a miss runs the HW8 pipeline (three qwen3 calls plus Kafka and a database lookup, about 5.3 s of GPU time here);
  priced at an API-equivalent ~0.003 USD per model call, three calls come to about 0.01 USD. A hit costs about nothing, so this is what a hit saves.
- C_FALSE = 2.5 USD: a false hit gives the user a confident wrong fixture fact; the cost is one support contact, about 5 minutes of league-staff time
  at 30 USD/hour. It ignores the cost of a player turning up at the wrong ground, so it is on the low side.
Both are assumptions (`code/cache_hw9/cost_model.py`), so the cheapest threshold is also computed for other values of C_FALSE:

| C_FALSE (USD) | cheapest threshold | its total (USD) |
|---|---|---|
| 0.01 | 0.75 | 0.25 |
| 0.05 | 0.95 | 0.68 |
| 0.25 | 0.95 | 2.68 |
| 2.5 | 0.95 | 25.18 |
| 25 | 0.95 | 250.18 |

**Threshold to ship: 0.95** (total 25.18 USD, the lowest in the sweep). A false hit is 250x as costly as a miss, so the
cheapest choice is the highest threshold: it loses 8 true hits but avoids the most wrong answers. It is not a good result in absolute terms:
10 false hits remain at 0.95, because the embedding cannot tell one fixture code from another. Raising the threshold is the wrong tool for that
failure; it needs a structural guard (for example, only serve a hit if the fixture codes in both queries are identical), which was not implemented because the assignment asks only to choose a threshold.

### 3.5 Stale answers and invalidation

Cached query: `How many player spots are available for fixture FX-9871-00013?` - depends on `fixtures.spots_available` of the single row FX-9871-00013. The row was changed from 22 to 17 and restored to 22 at the end.

| Step | Result |
|---|---|
| 1. first ask is a miss and the answer is cached | PASS - 22 player spots are available. |
| 2. repeat is a hit with the same answer | PASS - similarity=1.0 |
| 3a. control: a view-counter sync (updated_at changes) does NOT invalidate | PASS - updated_at 2026-11-06 15:43:10 -> 2026-11-06 15:52:00, still a hit |
| 3b. control: editing a different fixture does NOT invalidate | PASS -  |
| 4. database now says the new value (read directly) | PASS - 17 player spots are available. |
| 5. STALE HIT without a version check: cache still returns the old answer | PASS - cache says '22 player spots are available.'; database says '17 player spots are available.' |
| 6. with the version check: stale entry detected, pipeline re-run, fresh answer | PASS - new answer '17 player spots are available.', version 3878640e93bca289 -> 79ba45dd2a83ffc2 |
| 7. repeat is a hit with the fresh answer; exactly one entry (stale one deleted) | PASS - entries=1 |
| 8. cost of the check measured (30 hits each) | PASS - mean hit latency 8.32 ms without, 9.02 ms with |

Strategy: version check on hit. Each entry stores a data-version marker (a SHA-256 fingerprint of the fixture fields the answer was built from). On a hit,
the handler recomputes the fingerprint of the entry's rows from MySQL; if it differs, the entry is deleted and the question goes through the pipeline again
(step 6: version 3878640e93bca289 -> 79ba45dd2a83ffc2). The marker is a content fingerprint, not `updated_at`,
because `updated_at` also changes on every Part 1 view-counter sync (control 3a: it changed and the entry was correctly kept).

Trade-off: it never serves a stale answer for the fields it fingerprints, and it does not invalidate on unrelated edits, but every hit now pays a database read and the
cache depends on MySQL being reachable: mean hit latency was 8.32 ms without the check and 9.02 ms with it (30 hits each),
and a hit still cannot be served from Redis alone. A TTL would be cheaper per hit but would leave a window in which stale answers are served.
