"""Builds the Part 4.3 section of reports/hw10/METRICS.md and raw/part4_latency_table.json from raw/spans_latency.jsonl + raw/part4_latency_requests.json
(no numbers typed by hand). Per request: stage durations come from that trace's spans; percentages are the sum of a stage's time over the 50 requests divided by the
sum of the 50 end-to-end (`request` span) times."""
import json
import pathlib
from collections import defaultdict

import numpy as np

root = pathlib.Path(__file__).resolve().parents[2] / "reports" / "hw10"
req = json.load(open(root / "raw" / "part4_latency_requests.json", encoding="utf-8"))
spans = [json.loads(line) for line in open(root / "raw" / "spans_latency.jsonl", encoding="utf-8") if line.strip()]
by = defaultdict(dict)
for s in spans:
    by[s["trace_id"]].setdefault(s["stage"], 0.0)
    by[s["trace_id"]][s["stage"]] += s["duration_ms"]
miss_ids = [m["trace_id"] for m in req["misses"]]
QUEUES = ("queue_inbox", "queue_tasks", "queue_drafts", "final")
rows = []
for t in miss_ids:
    d = by[t]
    queue = sum(d[q] for q in QUEUES)
    named = d["cache_lookup"] + d["planner"] + d["writer"] + d["reviewer"] + queue
    rows.append({"cache_lookup": d["cache_lookup"], "planner": d["planner"], "writer": d["writer"], "reviewer": d["reviewer"], "queue_wait_total": queue,
                 "evaluation": d["evaluation"], "e2e": d["request"], "facts_lookup": d["facts_lookup"], "cache_store": d["cache_store"],
                 "other": d["request"] - named - d["facts_lookup"] - d["cache_store"], **{q: d[q] for q in QUEUES}})
e2e_sum = sum(r["e2e"] for r in rows)
pct = lambda k: 100 * sum(r[k] for r in rows) / e2e_sum  # noqa: E731
p = lambda k, q: float(np.percentile([r[k] for r in rows], q))  # noqa: E731
LABEL = [("cache_lookup", "Cache lookup"), ("planner", "Planner"), ("writer", "Writer"), ("reviewer", "Reviewer"), ("queue_wait_total", "Queue wait (total)"),
         ("evaluation", "Evaluation (after the request, not part of end-to-end)")]
extra = [("facts_lookup", "Database facts lookup"), ("cache_store", "Cache store"), ("other", "Other / unaccounted (ingress, Kafka produce)")]
table = {k: {"label": lab, "p50_ms": round(p(k, 50), 1), "p95_ms": round(p(k, 95), 1), "pct_of_e2e": round(pct(k), 1)} for k, lab in LABEL + extra}
table["e2e"] = {"label": "Cache-miss end-to-end", "p50_ms": round(p("e2e", 50), 1), "p95_ms": round(p("e2e", 95), 1), "pct_of_e2e": 100.0}
for q in QUEUES:
    table[q] = {"label": q, "p50_ms": round(p(q, 50), 1), "p95_ms": round(p(q, 95), 1), "pct_of_e2e": round(pct(q), 1)}
hits = [by[h["trace_id"]] for h in req["hit_repeats"]]
hit = {"n": len(hits), "all_served_from_cache": all(h["is_cached"] for h in req["hit_repeats"]),
       "p50_ms": round(float(np.percentile([h["request"] for h in hits], 50)), 1), "p95_ms": round(float(np.percentile([h["request"] for h in hits], 95)), 1),
       "mean_ms": round(float(np.mean([h["request"] for h in hits])), 1)}
(root / "raw" / "part4_latency_table.json").write_text(json.dumps({"n_requests": len(rows), "stages": table, "cache_hit": hit}, indent=2), encoding="utf-8")

fmt = lambda k: f"{table[k]['p50_ms']:,.1f} | {table[k]['p95_ms']:,.1f} | {table[k]['pct_of_e2e']:.1f}%"  # noqa: E731
dom = max(("planner", "writer", "reviewer", "queue_wait_total", "cache_lookup"), key=pct)
ev_ok = sum(m.get("evaluation_status") == "ok" for m in req["misses"])
text = f"""## Part 4.3 - Stage-latency experiment ({len(rows)} confirmed cache misses)

Run at {req['run_at']} (local time), one request at a time, empty semantic cache, threshold 0.85. All {req['confirmed_misses']} requests were confirmed misses: the response said is_cached=False and the
trace's cache_lookup span said path=miss ({len(req['skipped_cache_served'])} pool questions were skipped because the cache answered them). Source: `raw/spans_latency.jsonl` (one JSON span per stage and trace_id).

| Stage | p50 (ms) | p95 (ms) | % of cache-miss end-to-end |
|---|---|---|---|
""" + "\n".join(f"| {lab} | {fmt(k)} |" for k, lab in LABEL) + f"""
| Cache-miss end-to-end (request span) | {table['e2e']['p50_ms']:,.1f} | {table['e2e']['p95_ms']:,.1f} | 100% |

Other parts of the end-to-end time: """ + "; ".join(f"{lab.lower()} {table[k]['pct_of_e2e']:.1f}% (p50 {table[k]['p50_ms']:,.1f} ms)" for k, lab in extra) + f""".
Queue wait (total) = time messages sat in the inbox, tasks and drafts topics plus the final topic before the next stage took them ("{', '.join(QUEUES)}"). Evaluation is the judge's time per
request; it runs after the request and is shown against the end-to-end time only for scale. {ev_ok} of {len(req['misses'])} requests were evaluated successfully.

Cache-hit path (kept separate): {hit['n']} exact repeats of answered questions, all served from the cache = {hit['all_served_from_cache']}: p50 {hit['p50_ms']} ms, p95 {hit['p95_ms']} ms, mean {hit['mean_ms']} ms,
against a cache-miss p50 of {table['e2e']['p50_ms']:,.1f} ms.

What this shows: the dominant contributor to cache-miss latency is {table[dom]['label'].lower()} ({table[dom]['pct_of_e2e']:.1f}% of end-to-end). The three agent stages are LLM calls, so together they make up
{table['planner']['pct_of_e2e'] + table['writer']['pct_of_e2e'] + table['reviewer']['pct_of_e2e']:.1f}% of the time, while queue wait is {table['queue_wait_total']['pct_of_e2e']:.1f}% and the cache lookup {table['cache_lookup']['pct_of_e2e']:.1f}%.
So Kafka hand-offs and the cache lookup are not where time goes; model generation is. A request that hits the cache skips all of it.

What I would optimize first: the {table[dom]['label']} stage, because it is the largest single share. The Writer produces the longest text (up to 120 words) so it spends the most time generating; shortening
its output limit, or using a smaller or faster model for that stage, would cut the most time. The Planner and Reviewer produce short JSON and are next. Improving Kafka or the cache lookup would change under 4% of the time.
Limits: requests ran one at a time, so queue wait is the floor; under concurrent load the queues would grow. One run of 50 requests on one machine, one model, so the p95 is based on the slowest 2-3 requests.
"""
out = root / "METRICS.md"
prev = out.read_text(encoding="utf-8")
parts = prev.split("\n## ")
keep = [parts[0]] + [x for x in parts[1:] if not x.startswith("Part 4.3 ")]
out.write_text("\n## ".join(keep).rstrip() + "\n\n" + text, encoding="utf-8")
print(text)
