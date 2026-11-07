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

## Part 4 - Self-improving multi-agent system

Model: qwen3:8b (Ollama, thinking off, temperature 0, seed 9871). Run at 2026-11-06T19:29:07 (local time). Input files: 18 test, 14 validation and
14 training questions (`code/agents_hw9/data/`, questions only; the reference dataset holds all fixtures of `s9871_rel`).
The Evaluator is rule-based and reads only the reference dataset; the Answering Agent reads the same facts from MySQL and never sees the reference file.

### 4.4 Final test (test_data.json, each variant run once on the same 18 questions)

| Variant | Correct answers | Incorrect answers | Average attempts | Average latency (ms) |
|---|---|---|---|---|
| Baseline | 15 / 18 | 3 | 1 | 998.5 |
| Evaluator Repair | 18 / 18 | 0 | 1.17 | 1011.7 |
| Lesson Memory | 18 / 18 | 0 | 1.11 | 1049.2 |
| Validated Improvement | 18 / 18 | 0 | 1 | 839.4 |

A question counts as correct when the Evaluator's final verdict is PASS. First-answer failures per variant:

| Variant | Questions whose FIRST answer failed | Failure type |
|---|---|---|
| Baseline | tes_04, tes_05, tes_15 | UNSUPPORTED_ANSWER |
| Evaluator Repair | tes_04, tes_05, tes_15 | UNSUPPORTED_ANSWER |
| Lesson Memory | tes_06, tes_08 | OMITTED_FACT |
| Validated Improvement | none | - |

What this shows: without feedback the baseline gets 15 of 18 right; its 3 errors are all the same kind: off-topic questions ("Translate 'good morning' into Spanish."; "Explain how photosynthesis works."; "What is the tallest mountain in the world?")
answered from general knowledge instead of saying the data is not available. The Evaluator's feedback repaired all of them on the second attempt
(Evaluator Repair 18/18), at the cost of 1.17 attempts per question on average. The validated lesson lets the first answer be right
(Validated Improvement 18/18, average attempts 1). Lesson Memory, which loads every proposed lesson without validation, also ends with
18/18 correct but needed 1.11 attempts, because it also loaded the harmful controlled lesson (lesson_002, which was loaded on tes_06, tes_08; those needed a second attempt:
the Evaluator caught the omitted part and the repair loop fixed it, so the damage shows up as extra attempts and latency, not as a wrong final answer).
Average latency is nearly the same for Baseline and Evaluator Repair (998.5 and 1011.7 ms); the lower figure for Validated Improvement (839.4 ms) is mostly because the
refusals it now gives are very short answers, not a speed-up of the model. With 18 questions, a one-question difference is not strong evidence; qwen3 is not bit-reproducible, so another run can differ slightly.

### 4.1 Complete revision sequence (controlled test: the first answer is deliberately incomplete)

- Question: For fixture FX-9871-00005, which team is the home team and what is its home ground?
- Attempt 1 (forced for the test): The home team is Sunnyvale Falcons.
- Evaluator: REVISE - The answer leaves out requested information: home ground.
- Feedback: Your answer is missing: FX-9871-00005 home ground ('Fair Oaks Park'). Answer every part of the question using the facts provided.
- Attempt 2 (revised by the Answering Agent): The home team for fixture FX-9871-00005 is Sunnyvale Falcons, and its home ground is Fair Oaks Park.
- Evaluator: PASS - Every requested fact matches the reference data.
- Attempts: 2 (maximum 2). Final answer / result: The home team for fixture FX-9871-00005 is Sunnyvale Falcons, and its home ground is Fair Oaks Park. / PASS

### 4.2 Lessons and reuse

Training (12/14 correct on the first attempt) failed on tra_07, tra_12 - the same pattern (UNSUPPORTED_ANSWER) twice, so the Evaluator
proposed one lesson from it. A second candidate was added on purpose as a controlled test of the validation gate.

Kept lesson store (`code/agents_hw9/lessons.json`, use_count after the demonstration):

```json
[
  {
    "lesson_id": "lesson_001",
    "failure_pattern": "The answer states something the league facts do not support (unknown fixture, data the league does not record, or a question that is not about the league).",
    "correction": "If the provided facts do not contain what is asked, reply that you do not have that information; do not answer from general knowledge and do not guess.",
    "created_at": "2026-11-06",
    "use_count": 1,
    "failure_type": "UNSUPPORTED_ANSWER",
    "applies_when": [
      "no_data"
    ],
    "source": "training failures: tra_07, tra_12"
  }
]
```

Reuse demonstration, later question "Who painted the Mona Lisa?": without lessons the answer was "The Mona Lisa was painted by Leonardo da Vinci." (REVISE, UNSUPPORTED_ANSWER); with the store loaded
(lessons used: lesson_001) it was "I do not have that information." (PASS). use_count went {"lesson_001": 0} -> {"lesson_001": 1}
and the new value is in the file ({"lesson_001": 1}).

### 4.3 Validation (validation_data.json, one attempt per question so the lesson's own effect is measured)

Keep a lesson only if: no previously correct answer becomes wrong; at least one failing case is fixed; total failures do not increase; unsupported answers do not increase.

| Candidate lesson | Source | Fixed | Regressions | Failures before -> after | Unsupported before -> after | Decision |
|---|---|---|---|---|---|---|
| lesson_001 (UNSUPPORTED_ANSWER) | training failures: tra_07, tra_12 | val_04, val_12 | none | 2 -> 0 | 2 -> 0 | **KEEP** |
| lesson_002 (CONTROLLED_OVERBROAD) | controlled: deliberately harmful, to demonstrate the validation gate | none | val_02 | 0 -> 1 | 0 -> 0 | **REJECT** |

The rejected lesson ("controlled: deliberately harmful, to demonstrate the validation gate") told the agent to answer only the first part of a multi-part question. On val_02 it changed a previously correct answer into
a WRONG_FACT ('The fixture FX-9871-00910 is between Oakland Lions and Santa Clara Bears, and there are 22 spots left.'), so it was removed, as the assignment requires. Candidates: 2; kept: 1. test_data.json was not used to create or choose any lesson.

### Short explanations

- Agent communication: the controller passes plain JSON messages. To the Answering Agent: question, attempt number, and (on attempt 2) the Evaluator's feedback and its previous answer. From it: the answer and the lessons it used.
  To the Evaluator Agent: question and answer. From it: PASS or REVISE, an explanation, feedback and a failure type. The agents never share state other than these messages.
- Lesson reuse: before each answer the Answering Agent computes tags for the question (multi-part, no recorded data, names a fixture), loads the lessons whose `applies_when` matches, adds their corrections to its prompt and increments `use_count`.
- Stopping condition: at most two attempts. A PASS stops immediately; a REVISE after attempt 1 triggers one revision; after attempt 2 the system stops and reports the result whatever it is.
- Validation process: each candidate is added to the kept set, the validation questions are run before and after, and the four rules above decide. The test set is run only afterwards, once per variant.
- Limitation: the Evaluator recognises what a question asks with keyword patterns and checks the answer by string matching, so an unusual phrasing or a differently worded correct answer can be mis-scored; only 18 test questions were used, and
  the failures are concentrated in one pattern (answering off-topic questions), so the results do not show how the lessons would behave on other kinds of failure.
