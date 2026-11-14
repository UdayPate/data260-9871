"""Builds the Part 1 section of reports/hw10/METRICS.md from the dashboard's own test output (raw/part1_dashboard_test.txt) and the data files (no numbers typed by hand)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import data  # noqa: E402

root = pathlib.Path(__file__).resolve().parents[2] / "reports" / "hw10"
test = (root / "raw" / "part1_dashboard_test.txt").read_text(encoding="utf-8")
n_pass, n_fail = test.count("PASS "), test.count("FAIL ")
spans = data.load_spans()
s = data.summary(data.requests(spans))
files = sorted({x["source"] for x in spans})
ids = json.loads((root / "raw" / "part4_trace_ids.json").read_text(encoding="utf-8"))
text = f"""## Part 1 - Streamlit operations dashboard

`code/dashboard_hw10/app.py` (run: `streamlit run code/dashboard_hw10/app.py --server.port 8873`). It reads only the files the real runs wrote under `reports/hw10/raw`.
Spans: {', '.join(files)}. Results: part2_eval_results.json, part3_judge_scores.json, part4_trace_ids.json, part4_latency_table.json.

| Page | What it shows |
|---|---|
| Summary | request count, semantic-cache hit rate (hits and misses counted separately), error rate, end-to-end p50/p95 for misses and hits separately; each metric's caption states its data source and time window; the 50-miss stage table |
| Evaluation | Part 2 scores by stage (Planner / Writer / Reviewer output) and case with a chart and interpretation; Part 3 Spearman, mean absolute difference and repeatability with the per-case human-vs-judge table and chart |
| Trace lookup | `trace_id` input (plus buttons for the three required traces); stages in order with start, end, duration, status and error; cache HIT / MISS / FAILED banner; timeline chart |

Current values on the Summary page (all recorded runs): {s['requests']} requests, {s['hits']} hits / {s['misses']} misses ({s['hit_rate_pct']}% hit rate), {s['errors']} error ({s['error_rate_pct']}% error rate).
These are the traces recorded by the HW10 experiments, not live traffic, and the latency experiment deliberately asked 50 new questions, so the hit rate reflects how the experiments were designed.
Caching: `@st.cache_data` for loading the span and result files (refreshed when a file changes) and `@st.cache_resource` for the trace_id index shared by all sessions.

Checks: `code/dashboard_hw10/test_dashboard.py` runs the real app headlessly (Streamlit AppTest) and compares what each page shows with an independent count of the span files:
{n_pass} passed, {n_fail} failed (`raw/part1_dashboard_test.txt`). The five screenshots (`reports/hw10/screenshots/`) were taken by `take_screenshots.py` (headless Chromium via Playwright): the Summary and Evaluation
pages and the Trace lookup page for the miss ({ids['cache_miss_success']['trace_id'][:8]}), hit ({ids['cache_hit']['trace_id'][:8]}) and failed ({ids['failed']['trace_id'][:8]}) traces, typed into the input box.
"""
out = root / "METRICS.md"
prev = out.read_text(encoding="utf-8")
parts = prev.split("\n## ")
keep = [parts[0]] + [x for x in parts[1:] if not x.startswith("Part 1 ")]
out.write_text("\n## ".join(keep).rstrip() + "\n\n" + text, encoding="utf-8")
print(text)
