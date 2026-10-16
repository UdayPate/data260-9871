# HW6 Metrics (SID4 9871, seed 9871)

Model: `qwen3:8b` via Ollama (thinking disabled, temperature 0.3), embeddings `all-MiniLM-L6-v2`.
All numbers below come from `raw/part3_turns.csv`, `raw/part3_probes.json`, `raw/part3_summary.json`
and were recomputed by `code/doc_api/analyze_part3.py` (output in `RUN_LOG.txt`).

## Part 3 - What memory costs

Method: the same fixed 30-message conversation (`code/doc_api/part3_conversation.json`; five probe
facts planted at turns 1, 4, 8, 15, 23) in a fresh user/session per run, then the five probes from
`memory_probes.yaml` asked with `read_only=true`. Each setting was run **3 times with seeds 9871, 9872,
9873** (90 measured turns per setting; a warm-up call precedes every run). "N" counts *messages*
(user + assistant), so N=30 is the last 15 turns. Episodic top-k = 3 and summaries every 6 user
messages in the three N settings.

### Required table (means over 3 runs x 30 turns; probe score = mean of 5 probes x 3 runs)

| Setting | Mean prompt tokens/turn (reply call) | Mean latency (ms), reply call | Mean latency (ms), whole request | Probe quality (1-5) |
|---|---:|---:|---:|---:|
| SHORT_TERM_N=4 | 425.6 | 1600 | 3329 | 5.00 |
| SHORT_TERM_N=12 | 665.8 | 2093 | 4064 | 5.00 |
| SHORT_TERM_N=30 | 1050.0 | 2005 | 4200 | 5.00 |
| Compression policy (keep last 6 + summary every 3) | 501.9 | 1583 | 4190 | 4.33 |

"Reply call" is the one model call that answers the user (what `SHORT_TERM_N` changes). "Whole
request" also includes the extra calls every turn makes for episode extraction and, periodically,
summarisation. Mean prompt tokens per turn counting *all* calls: 705.9 / 952.8 / 1338.8 / 878.1.

Variation across the three seeds: probe score per run was 5.0/5.0/5.0 for all three N settings and
4.6/4.6/3.8 for compression. Reply-prompt-token means per run ranged 416-435 (N=4), 652-685 (N=12),
1029-1068 (N=30), 482-512 (compression).

### Where the prompt tokens go (mean per turn, reply call)

| Setting | System primer | Long-term summary | Short-term window | Episodic facts | Current msg | Chat-template overhead |
|---|---:|---:|---:|---:|---:|---:|
| N=4 | 48.0 | 178.2 | 105.9 | 47.9 | 13.1 | 32.5 |
| N=12 | 48.0 | 179.6 | 324.0 | 47.9 | 13.1 | 53.1 |
| N=30 | 48.0 | 186.7 | 666.8 | 47.9 | 13.1 | 87.5 |
| Compression | 48.0 | 196.3 | 158.7 | 47.9 | 13.1 | 37.9 |

Components are counted with the Qwen3 tokenizer on each component's text; "template overhead" is
`prompt_tokens (from Ollama) - sum of components` (role markers etc.).

### Compression/eviction policy: token savings and quality change

Policy: only the last 6 raw messages stay in the prompt; older turns survive only through the session
summary, which is regenerated every 3 user messages (instead of every 6).

| Compared with | Reply prompt tokens/turn | All-call prompt tokens/turn | Probe quality |
|---|---|---|---|
| N=30 (full-history baseline) | 1050.0 -> 501.9 (**52.2% saved**) | 1338.8 -> 878.1 (**34.4% saved**) | 5.00 -> 4.33 |
| N=4 (for reference) | 425.6 -> 501.9 (18% *more*) | 705.9 -> 878.1 (24% *more*) | 5.00 -> 4.33 |

### Estimated cost of 10,000 x 30-turn conversations (input $1/M tokens, output $5/M tokens)

| Setting | Counting every model call | Reply call only |
|---|---:|---:|
| N=4 | **$350.83** (best) | $186.61 |
| N=12 | $435.38 | $268.18 |
| N=30 | **$552.86** (worst) | $382.85 |
| Compression | $438.66 | $211.13 |

Selection rule (fixed before the sweep was run): *worst* = most expensive setting; *best* = cheapest
setting whose mean probe score is within 0.5 of the highest score (5.00, so >= 4.50). Compression
(4.33) was ineligible; among N=4/12/30 (all 5.00) the cheapest is N=4. The "all model calls" column is
the honest cost figure: every turn also pays for episode extraction, and summarisation calls add more.
No hosted-model run was made: tokens were measured on the local Qwen3 tokenizer, so a hosted model
with a different tokenizer would count somewhat differently.

### What the results show (plain language)

1. **Window size drives cost, not recall.** Going from N=4 to N=30 raised reply-prompt tokens by 2.5x
   and the 10,000-conversation bill by 58% ($351 -> $553), yet all three scored a perfect 5.00 on every
   probe in every run. The facts survived in long-term memory (session/lifetime summaries and
   episodic facts), so the larger raw window bought nothing measurable here.
2. **These probes cannot separate the N settings.** Because every probed fact was also in a summary or
   an episode, the probes test the *whole* memory system, not the short-term window alone. A harder test
   (e.g. disabling summaries/episodes, or facts that never get summarised) would be needed to show what
   a bigger window protects. Reported as a limitation, not a win for small N.
3. **The summary is the biggest fixed cost for small windows.** At N=4 the long-term summary (178 tokens)
   is larger than the window (106).
4. **The compression policy saved tokens but cost quality, and was beaten by plain N=4.** It cut reply
   prompt tokens 52% versus N=30, but only 34% over all calls (summarising every 3 messages adds model
   calls; mean completion tokens per turn rose to 116.8 vs about 93-101), and whole-request latency did
   not improve (4190 ms vs 4200 ms). Probe quality fell to 4.33. The stored data shows why: in the
   compression runs the word "November" appeared in **0 of 15** summaries in every one of the 3 runs
   (it appeared in 7 of 7 summaries in each of the 9 N=4/12/30 runs; checked directly in MongoDB), because
   shorter, more frequent summaries (each built from only the last 6 messages and capped at 5 bullets)
   dropped older details. For P2 the model then invented "Mondays and Fridays"/"Tuesdays and Thursdays"
   for the assistant coach's unavailability (score 3 in all 3 runs), and in one run it said no food
   restriction had been mentioned (P3, score 1). N=4 was both cheaper and better than compression.
5. **Latency:** the reply-call latency differences between settings (1.6-2.1 s) are small and not
   monotonic in N (N=12 > N=30), so with 90 turns per setting on one local GPU they should be read as
   "roughly similar", not as a measured effect.

### Scoring notes
- Scores come from the deterministic keyword rubric in `memory_probes.yaml`, applied by
  `run_part3_sweep.py`; every answer is stored verbatim in `raw/part3_probes.json`. I read the N=4 answers
  for run 1 and every non-5 compression answer by hand: the scorer agreed with my reading each time.
- `memory_probes.yaml` was edited once after the smoke test (P5 contradiction phrases widened) and
  before the full sweep; the smoke test found that "email *and text* message" scored 5.
- Caveats: only 5 probes per run (coarse), 3 seeds per setting, and temperature 0.3 means the model is
  not fully deterministic even with a fixed seed.

## Part 2 notes
- `GET /api/aggregate/{user_id}` groups message counts by **UTC** date.
- The final Part 2 test run: 17/17 checks; two prompt bugs found by reading transcripts and fixed
  (see `RUN_LOG.txt`).

## Part 4
_(to be filled in after Part 4)_
