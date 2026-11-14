# HW10 METRICS

## Part 2 - Automated evaluation of the Kafka pipeline

Run at 2026-11-10T12:02:49 (local time). 6 of 6 requests evaluated (collect: 20 messages read, 0 malformed skipped).
Judge: DeepEval GEval with a 5-band rubric, local qwen3:8b via Ollama, temperature 0, seed 9871, thinking off, 120 s timeout per call. Scale: 1 (very poor) to 5 (excellent).
The judge sees the same question text the Planner saw (the database facts plus the question).

| # | question | trace | Plan Quality | Writer Helpfulness | Final Helpfulness | final - draft | final text = draft | Reviewer status |
|---|---|---|---|---|---|---|---|---|
| 1 | Which team is the home team for fixture FX-9871-00012? | 5b53057f | 3 | 3 | 3 | +0 | yes | approved |
| 2 | What should a league office check before scheduling a Soccer fixture o | 10cd3bf1 | 2 | 3 | 2 | -1 | yes | approved |
| 3 | How should a league office handle a team that cannot field enough play | 688bc472 | 2 | 3 | 3 | +0 | yes | approved |
| 4 | Explain how a round-robin schedule works for a six-team volleyball lea | 6cb93999 | 2 | 2 | 2 | +0 | yes | rejected |
| 5 | What information belongs in a fixture cancellation notice sent to both | 556edd3c | 2 | 3 | 3 | +0 | yes | approved |
| 6 | Why might a league cap the number of substitutions in a cricket match? | 5f2dffb3 | 2 | 3 | 3 | +0 | yes | approved |

| Stage | Mean score (1-5) |
|---|---|
| Plan Quality (Planner) | 2.17 |
| Writer Helpfulness (Writer draft) | 2.83 |
| Final Answer Helpfulness (Reviewer output) | 2.67 |
| Mean final - draft | -0.17 (min -1, max +0) |
| Requests where the final text is identical to the draft | 6 of 6 |

What this shows: the final answer did not improve on the draft in any request (mean difference -0.17). The reason is structural, not a judge effect: the Reviewer does not rewrite, it only approves or rejects,
so in 6 of 6 requests the final answer is the Writer's draft word for word. A non-zero difference on identical text is therefore judge variation between two differently worded criteria, not an improvement.
The Planner's plans scored lowest (mean 2.17); in requests 3 to 6 (all scored 2) the judge's reasons say the steps are relevant but lack specificity or completeness.
The judge is not perfectly consistent with itself: for request 2 its reason calls the plan specific, ordered and complete, yet the score is 2. Part 3 measures this judge against human labels.
6 requests is a small sample, so these means are indicative only.

## Part 3 - Validating the judge

Run at 2026-11-12T12:02:09 (local time). Judge: Writer Helpfulness (GEval, 5-band rubric), local qwen3:8b, temperature 0, seed 9871, thinking off, scale 1 (very poor) to 5 (excellent).
The 20 drafts (`eval_cases.json`) and the human labels (`human_labels.csv`) were committed before this run; their SHA-256 (line endings normalised) are
916e0bea895375a6... and 886be97023caa475... in `raw/part3_judge_scores.json`. The judge ran 3 times on the same inputs and settings.

| case | question | human | judge run 1 | run 2 | run 3 | judge - human (run 1) |
|---|---|---|---|---|---|---|
| case_01 | Which team is the home team for fixture FX-9871-00012? | 5 | 5 | 5 | 5 | +0 |
| case_02 | How many player spots are still open on fixture FX-9871-00031, | 5 | 3 | 3 | 3 | -2 |
| case_03 | Where will fixture FX-9871-00044 be played? | 5 | 5 | 5 | 5 | +0 |
| case_04 | Name both teams in fixture FX-9871-00057 and say which one is  | 2 | 2 | 2 | 2 | +0 |
| case_05 | Is there room for 3 more players to register for fixture FX-98 | 5 | 5 | 5 | 5 | +0 |
| case_06 | What is the name of fixture FX-9871-00078? | 5 | 5 | 5 | 5 | +0 |
| case_07 | Which team is the home team for fixture FX-9871-09101? | 5 | 2 | 2 | 2 | -3 |
| case_08 | How many player spots are open on fixture FX-9871-09102? | 4 | 2 | 2 | 2 | -2 |
| case_09 | What should a league office check before scheduling a Soccer f | 4 | 3 | 3 | 3 | -1 |
| case_10 | How should a league office handle a team that cannot field eno | 4 | 5 | 5 | 5 | +1 |
| case_11 | Explain how a round-robin schedule works for a six-team volley | 3 | 2 | 2 | 2 | -1 |
| case_12 | What information belongs in a fixture cancellation notice sent | 4 | 3 | 3 | 3 | -1 |
| case_13 | Why might a league cap the number of substitutions in a cricke | 2 | 2 | 2 | 2 | +0 |
| case_14 | What are three ways to reduce no-shows for early-morning baske | 3 | 2 | 2 | 2 | -1 |
| case_15 | How do you break a tie in league standings when two teams have | 3 | 2 | 2 | 2 | -1 |
| case_16 | What was the final score of last season's championship game? | 1 | 5 | 5 | 5 | +4 |
| case_17 | What is the phone number of the league office? | 1 | 5 | 5 | 5 | +4 |
| case_18 | Which referee is assigned to fixture FX-9871-00012? | 5 | 2 | 2 | 2 | -3 |
| case_19 | How much does it cost to register a team this season? | 1 | 3 | 3 | 3 | +2 |
| case_20 | Summarise the weather forecast for this Saturday's fixtures. | 1 | 3 | 3 | 3 | +2 |

| Statistic | Value |
|---|---|
| Spearman rank correlation, human vs judge (run 1) | 0.1468 (p = 0.5367, n = 20) |
| Mean absolute difference, human vs judge | 1.4 / 1.4 / 1.4 (runs 1 / 2 / 3) |
| Mean judge score minus mean human label | -0.1 |
| Exact agreement / within 1 point (run 1) | 30.0% / 60.0% |
| Cases whose score changed across the 3 runs | 0 of 20 (0.0%) |
| Run pairs where a score changed | 0 of 60 (0.0%) |
| Mean / maximum absolute change between runs | 0 / 0 |

What this shows: the judge is perfectly repeatable but weakly valid. Its scores did not change in any of the 60 run-to-run comparisons, which is expected with temperature 0 and a fixed seed, so this
measures determinism, not robustness: it says nothing about how the score moves if the wording of the draft or the prompt changes. Agreement with the human labels is weak: Spearman 0.1468
(p = 0.5367, so not distinguishable from no correlation at n = 20) and an average miss of 1.4 points on a 5-point scale. The similar mean scores
(difference -0.1) hide errors in both directions.

The errors are systematic. In 4 of the 6 drafts the human rated 1 or 2 (case_16, case_17, case_19, case_20), the judge rated 3 or higher: these are drafts that state a score, a phone number, a fee or a forecast that the system has no data for.
The judge's reasons say the draft "directly addresses the question", so it rewards answering over being supported. In the other direction, 3 drafts the human rated 4 or 5 (case_07, case_08, case_18) got 2 or lower: the judge penalised
answers that correctly say the information does not exist or is not in the database.

Would I trust this judge to gate a deployment? No. A gate must catch unsupported answers, and this judge scores several invented answers higher than correct refusals. Evidence I would require first: (1) a Spearman correlation with human
labels clearly above chance on a larger set (at least 100 labelled drafts, ideally labelled by more than one person so human-human agreement is known); (2) a criterion that checks the draft against the supplied facts, so that unsupported answers
score low, then re-validated on the same labels; (3) a check of the judge under changes (paraphrased drafts, a different seed, a second judge model), since repeatability under a fixed seed is not robustness; (4) an agreed error budget,
for example at most one unsupported answer in 20 passed by the gate. The labels were written by one person on 20 cases, so these statistics are indicative only.

## Part 4.3 - Stage-latency experiment (50 confirmed cache misses)

Run at 2026-11-12T12:49:42 (local time), one request at a time, empty semantic cache, threshold 0.85. All 50 requests were confirmed misses: the response said is_cached=False and the
trace's cache_lookup span said path=miss (0 pool questions were skipped because the cache answered them). Source: `raw/spans_latency.jsonl` (one JSON span per stage and trace_id).

| Stage | p50 (ms) | p95 (ms) | % of cache-miss end-to-end |
|---|---|---|---|
| Cache lookup | 18.1 | 27.7 | 0.3% |
| Planner | 2,070.1 | 2,442.5 | 29.5% |
| Writer | 3,403.0 | 3,918.1 | 46.7% |
| Reviewer | 1,469.3 | 1,700.8 | 20.7% |
| Queue wait (total) | 202.7 | 217.6 | 2.8% |
| Evaluation (after the request, not part of end-to-end) | 16,344.5 | 17,250.3 | 227.0% |
| Cache-miss end-to-end (request span) | 7,275.9 | 8,117.2 | 100% |

Other parts of the end-to-end time: database facts lookup 0.0% (p50 0.0 ms); cache store 0.0% (p50 1.2 ms); other / unaccounted (ingress, kafka produce) 0.0% (p50 2.3 ms).
Queue wait (total) = time messages sat in the inbox, tasks and drafts topics plus the final topic before the next stage took them ("queue_inbox, queue_tasks, queue_drafts, final"). Evaluation is the judge's time per
request; it runs after the request and is shown against the end-to-end time only for scale. 50 of 50 requests were evaluated successfully.

Cache-hit path (kept separate): 10 exact repeats of answered questions, all served from the cache = True: p50 15.8 ms, p95 21.0 ms, mean 16.5 ms,
against a cache-miss p50 of 7,275.9 ms.

What this shows: the dominant contributor to cache-miss latency is writer (46.7% of end-to-end). The three agent stages are LLM calls, so together they make up
96.9% of the time, while queue wait is 2.8% and the cache lookup 0.3%.
So Kafka hand-offs and the cache lookup are not where time goes; model generation is. A request that hits the cache skips all of it.

What I would optimize first: the Writer stage, because it is the largest single share. The Writer produces the longest text (up to 120 words) so it spends the most time generating; shortening
its output limit, or using a smaller or faster model for that stage, would cut the most time. The Planner and Reviewer produce short JSON and are next. Improving Kafka or the cache lookup would change under 4% of the time.
Limits: requests ran one at a time, so queue wait is the floor; under concurrent load the queues would grow. One run of 50 requests on one machine, one model, so the p95 is based on the slowest 2-3 requests.

## Part 4.1 / 4.2 - Trace propagation and the three required traces

One identifier per request: the `trace_id` of every span is the HW8 `correlation_id` (the same value is in the Kafka messages), so nothing is joined afterwards. Each stage writes one JSON span with
trace_id, stage, start, end, status and error (`code/kafka_hw8/tracing.py`; the spans of all three traces are in `raw/spans_traces.jsonl`). `queue_*` spans are the time a message waited in a
topic before the next stage took it (from the Kafka message timestamp); `final` is the ingress receiving the Reviewer's answer; `request` is the whole request.

### Cache MISS, successful - trace_id 2505a50d-07d2-4fa4-aa1a-df8b550bcd6c
Question: Which team is the home team for fixture FX-9871-00012?

| # | stage | start | end | duration (ms) | status | error / details |
|---|---|---|---|---|---|---|
| 1 | request | 11:46:52.024 | 11:46:56.086 | 4,062.4 | ok | path=miss, pipeline_status=approved |
| 2 | cache_lookup | 11:46:52.024 | 11:46:52.035 | 11.0 | ok | path=miss |
| 3 | facts_lookup | 11:46:52.035 | 11:46:52.066 | 30.7 | ok |  |
| 4 | queue_inbox | 11:46:52.067 | 11:46:52.069 | 3.0 | ok |  |
| 5 | inbox | 11:46:52.067 | 11:46:52.069 | 2.0 | ok |  |
| 6 | planner | 11:46:52.069 | 11:46:54.159 | 2,089.1 | ok | attempts=1 |
| 7 | queue_tasks | 11:46:54.159 | 11:46:54.210 | 51.1 | ok |  |
| 8 | writer | 11:46:54.210 | 11:46:55.163 | 953.8 | ok | attempts=1 |
| 9 | queue_drafts | 11:46:55.164 | 11:46:55.207 | 43.4 | ok |  |
| 10 | reviewer | 11:46:55.207 | 11:46:56.081 | 874.4 | ok | attempts=1 |
| 11 | final | 11:46:56.082 | 11:46:56.084 | 3.0 | ok | pipeline_status=approved |
| 12 | cache_store | 11:46:56.085 | 11:46:56.086 | 0.5 | ok | stored=True |

### Cache HIT - trace_id 6f8c8309-bd42-4daa-9646-44f334e887a0
Question: Which team is the home team for fixture FX-9871-00012? (the same question asked again)

| # | stage | start | end | duration (ms) | status | error / details |
|---|---|---|---|---|---|---|
| 1 | request | 11:46:56.087 | 11:46:56.097 | 10.5 | ok | path=hit, pipeline_status=approved |
| 2 | cache_lookup | 11:46:56.087 | 11:46:56.097 | 10.1 | ok | path=hit, similarity=1.0 |

### FAILED - trace_id 5c4340ff-061d-4449-8e23-17e884e13047
Question: How many open player slots are left on fixture FX-9871-00031?. The Writer process was replaced by one whose model endpoint was unreachable (OLLAMA_HOST pointed at a closed port), so a real failure was produced rather than a simulated one.

| # | stage | start | end | duration (ms) | status | error / details |
|---|---|---|---|---|---|---|
| 1 | request | 11:47:05.803 | 11:47:51.039 | 45,235.7 | error | pipeline status=timeout |
| 2 | cache_lookup | 11:47:05.803 | 11:47:05.819 | 15.2 | ok | path=miss, similarity=0.4509 |
| 3 | facts_lookup | 11:47:05.820 | 11:47:05.821 | 1.0 | ok |  |
| 4 | queue_inbox | 11:47:05.822 | 11:47:05.824 | 2.4 | ok |  |
| 5 | inbox | 11:47:05.822 | 11:47:05.823 | 1.7 | ok |  |
| 6 | final | 11:47:05.823 | 11:47:51.039 | 45,215.8 | error | no message on s9871_final within 45 s |
| 7 | planner | 11:47:05.824 | 11:47:08.216 | 2,392.4 | ok | attempts=1 |
| 8 | queue_tasks | 11:47:08.217 | 11:47:08.274 | 57.5 | ok |  |
| 9 | writer | 11:47:08.274 | 11:47:18.582 | 10,308.3 | error | ConnectError: [WinError 10061] No connection could be made because the target machine actively refused it |
| 10 | cache_store | 11:47:51.039 | 11:47:51.039 | 0.0 | ok | stored=False |

What this shows: the hit trace has only `cache_lookup` (path=hit, 10.1 ms) and the `request` span; no Kafka stage runs. The miss trace has every stage in order
(cache_lookup, facts_lookup, inbox, planner, writer, reviewer, final, cache_store) with 3 queue-wait spans between the agents. In the failed trace the failing stage is **writer**:
three attempts, error `ConnectError: [WinError 10061] No connection could be made because the target machine actively refused it`, after which the message was dead-lettered; the ingress then found no answer on the final topic within 45 s, so `final` and `request` carry the status error too, and nothing was cached.
The trace identifies where it failed (writer) and the symptom the caller saw (no answer), which the single `request` span would not.

## Part 1 - Streamlit operations dashboard

`code/dashboard_hw10/app.py` (run: `streamlit run code/dashboard_hw10/app.py --server.port 8873`). It reads only the files the real runs wrote under `reports/hw10/raw`.
Spans: spans_latency.jsonl, spans_part2.jsonl, spans_traces.jsonl. Results: part2_eval_results.json, part3_judge_scores.json, part4_trace_ids.json, part4_latency_table.json.

| Page | What it shows |
|---|---|
| Summary | request count, semantic-cache hit rate (hits and misses counted separately), error rate, end-to-end p50/p95 for misses and hits separately; each metric's caption states its data source and time window; the 50-miss stage table |
| Evaluation | Part 2 scores by stage (Planner / Writer / Reviewer output) and case with a chart and interpretation; Part 3 Spearman, mean absolute difference and repeatability with the per-case human-vs-judge table and chart |
| Trace lookup | `trace_id` input (plus buttons for the three required traces); stages in order with start, end, duration, status and error; cache HIT / MISS / FAILED banner; timeline chart |

Current values on the Summary page (all recorded runs): 69 requests, 11 hits / 58 misses (15.9% hit rate), 1 error (1.4% error rate).
These are the traces recorded by the HW10 experiments, not live traffic, and the latency experiment deliberately asked 50 new questions, so the hit rate reflects how the experiments were designed.
Caching: `@st.cache_data` for loading the span and result files (refreshed when a file changes) and `@st.cache_resource` for the trace_id index shared by all sessions.

Checks: `code/dashboard_hw10/test_dashboard.py` runs the real app headlessly (Streamlit AppTest) and compares what each page shows with an independent count of the span files:
17 passed, 0 failed (`raw/part1_dashboard_test.txt`). The five screenshots (`reports/hw10/screenshots/`) were taken by `take_screenshots.py` (headless Chromium via Playwright): the Summary and Evaluation
pages and the Trace lookup page for the miss (2505a50d), hit (6f8c8309) and failed (5c4340ff) traces, typed into the input box.
