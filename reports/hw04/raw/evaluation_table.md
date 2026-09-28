## Per-question results

| Q | Config | Correct retrieval | Correct answer | Grounded | Refused when needed | Cites source |
|---|---|---|---|---|---|---|
| q1 | A | n/a | NO | n/a | n/a | NO |
| q1 | B | yes | yes | yes | n/a | NO |
| q1 | C | yes | yes | yes | n/a | yes |
| q2 | A | n/a | NO | n/a | n/a | NO |
| q2 | B | yes | yes | yes | n/a | NO |
| q2 | C | yes | yes | yes | n/a | yes |
| q3 | A | n/a | NO | n/a | n/a | NO |
| q3 | B | NO | NO | yes | n/a | NO |
| q3 | C | NO | NO | yes | n/a | yes |
| q4 | A | n/a | yes | n/a | n/a | NO |
| q4 | B | n/a | NO | yes | n/a | NO |
| q4 | C | n/a | NO | yes | n/a | yes |
| q5 | A | n/a | NO | n/a | NO | NO |
| q5 | B | n/a | NO | NO | NO | NO |
| q5 | C | n/a | yes | yes | yes | yes |
| q6 | A | n/a | NO | n/a | NO | NO |
| q6 | B | n/a | NO | NO | NO | NO |
| q6 | C | n/a | yes | yes | yes | NO |

## Summary

| Config | Accuracy | Faithfulness | Format compliance | Robustness (Q3-Q6) |
|---|---|---|---|---|
| A: No RAG | 17% | n/a | n/a | 25% |
| B: Basic RAG | 33% | 67% | n/a | 0% |
| C: Context-engineered | 67% | 100% | 100% | 50% |

Definitions: accuracy = share of the 6 questions handled as expected (right answer, or a refusal where one was needed); faithfulness = share of RAG answers supported by the context they were given; format compliance = share of config C answers that cite a [n] source or use the exact refusal sentence (A and B were never told to, so n/a); robustness = accuracy on the four stress questions Q3-Q6. All values are automatic heuristics - check them against the saved raw answers.