# AI_USE.md - HW11

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code as a tutor and debugging assistant while working on HW11. It helped me understand the assignment and starter kit, explained concepts when I was confused, and guided me whenever I was stuck or encountered an error. It also helped me create initial drafts of the policy, the three fictional companies' fixtures, the golden labels, the Yahoo price source, and some fixes in `watch.py`, `verify_hw11.py`, and the report generator.

I installed the kit on Muse and ran every required prompt myself, including the setup, scheduled task, crash, restart, duplicate, retry, injection, blocked-link, and metrics tests. I pasted the output back into the session, reviewed the usage page and results, made the project decisions, and ran all of the Git commands myself. I also committed the golden labels before running Muse so that the evaluation results would not affect the labels.

## 2. One mistake, how it was caught, and how it was fixed

My first live `run stock-watch` on Muse reported “0 new, 0 alerts.” Although this looked like a successful run, it was suspicious because the four companies each had five 8-K filings that should have been detected. The starter kit did not clearly report when one of its live data sources failed.

## 3. How did you detect the problem or verify the result?

I asked Muse for the trace from the run. It showed two `source_error` steps. The `prices_live` source failed with “Remote end closed connection without response,” and the `edgar_live` source failed with “HTTP Error 400: Bad Request.” Claude Code helped me reproduce both problems with `curl`. I found that EDGAR rejected `count=5` because the count must be at least 10, while Stooq was returning a JavaScript bot-check page instead of CSV data.

## 4. What did you change, and why does it work now?

I changed `per_company` to 10, added a `max_age_days` filter so the first run would stay manageable, and changed the live price source to Yahoo's chart API. After these changes, a second live run found 8 new items and generated 3 alerts. The source errors are still recorded only in the trace, so I documented that remaining limitation in Part 7 of the report.