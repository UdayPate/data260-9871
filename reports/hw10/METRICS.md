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
