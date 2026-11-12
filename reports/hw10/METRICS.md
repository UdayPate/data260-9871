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
