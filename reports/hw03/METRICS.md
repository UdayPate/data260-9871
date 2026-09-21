# METRICS — HW3 Part 2: Chunking Technique Comparison

## Retrieval Quality Comparison

| Technique | Chunks | Avg chunk length (chars) | Top-1 cosine | Mean@k cosine | Recall@k | Mean retrieval latency (ms) |
|---|---|---|---|---|---|---|
| Token | 254 | 952.8 | 0.7156 | 0.6684 | 5/5 | 18.51 |
| Semantic | 109 | 2,055.2 | 0.6277 | 0.5928 | 4/5 | 14.69 |
| Sentence-window | 2,020 | 110.9 | 0.6987 | 0.6339 | 5/5 | 55.73 |

(k=3, averaged across the 5 questions in `questions.yaml`. See
`reports/hw03/raw/chunking_comparison_raw.json` for the full per-query,
per-technique retrieval data, and `reports/hw03/raw/final_summary_table.json`
for these computed aggregates.)

## Confidently-scored retrieval that does not contain the answer

**Question:** "In AYSO soccer, how many players per side are allowed on the
field for the 8U age division, and are goalkeepers used?"
(expected source: `soccer_ayso_national_rules.txt`)

**What Semantic chunking retrieved instead:** all three top-k results came
from `soccer_ayso_basic_rules.txt` — a different AYSO document — with a
confident top cosine similarity of 0.7193.

**Why the embedding likely considered it similar:** both documents are AYSO
soccer rulebooks that discuss overlapping topics (team size by age
division, "Law 3: The Number Of Players," referee/equipment rules) using
very similar vocabulary. However, they are different editions —
`soccer_ayso_basic_rules.txt` is the 2009-2010 booklet, while
`soccer_ayso_national_rules.txt` is the 06/2018 national rules document —
and they actually state different numbers for the same age group (the
basic booklet says "5-a-side for U-8"; the national rules table says
"8U: 4-a-side, no goalkeepers"). The embedding captures topical similarity
("this is about AYSO team sizes by age") but cannot distinguish "this is
the current, precise answer" from "this is an older, approximate
statement on the same topic" - a genuine real-world corpus issue (two
documents from the same organization, topically near-identical, but
reflecting different rule editions).

A second, related pattern appeared across all three techniques for this
same question: the AYSO national rules team-size table has many
consecutive, nearly-identically-formatted rows (18U, 16U, 14U, 12U, 10U,
8U, 6U). Token and Sentence-window sometimes retrieved adjacent rows
(e.g. 6U or 18U/16U/14U) rather than precisely the 8U row - again because
the embedding matches on the table's overall structure and phrasing
rather than the one differing number.

## Observations

Token chunking performed best on this corpus across every retrieval
quality metric (highest top-1 cosine, highest mean@k cosine, perfect
5/5 recall) while also being fast. This corpus consists of plain
regulatory/rulebook prose without strong natural "topic shift" signals,
so Semantic chunking's boundary-detection had little to work with - it
under-split the text into fewer, much larger chunks (avg 2,055 chars,
with one outlier reaching 12,544 chars), which dilutes a specific fact
inside a large block of loosely related text and lowers similarity
scores. Sentence-window chunking, at the opposite extreme, achieved
perfect recall and occasionally pinpoint-precise single-sentence matches
(e.g. for the Fort Collins volleyball time-limit question, it retrieved
exactly the sentence "Time Limit: There will be a one (1) hour time
limit for the match."), but its very fine granularity (2,020 chunks
averaging only 111 characters) meant searching over far more chunks at
retrieval time, roughly tripling latency compared to Token (55.7ms vs.
18.5ms) without matching Token's overall similarity scores.

The one recall failure (Semantic, described above) did not repeat across
other queries - no other technique's best-scored result missed its
expected source file entirely, though near-miss row confusion (the
8U/6U table-row issue) appeared in multiple techniques for that same
question, suggesting this specific query (asking for one numeric value
buried in a repetitive table) was the hardest of the five regardless of
chunking strategy.

## Conclusion

For this corpus (community sports league rulebooks), Token-based
chunking is the best choice for deployment. It achieved the highest
retrieval quality on every measured metric (top-1 cosine, mean@k cosine,
and perfect recall) while keeping latency low - roughly a third of
Sentence-window's latency for better similarity scores. Semantic
chunking's theoretical advantage (finding natural topic boundaries) did
not pay off here because this corpus's plain, structurally repetitive
regulatory prose lacks the strong topic shifts that technique is
designed to detect, causing it to under-split and dilute specific facts
inside overly large chunks. Sentence-window chunking is worth
considering as a secondary technique specifically when pinpoint,
single-fact precision matters more than latency, but its 3x latency cost
is hard to justify here given Token already matches its recall while
scoring higher on similarity.