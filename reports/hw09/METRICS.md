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
