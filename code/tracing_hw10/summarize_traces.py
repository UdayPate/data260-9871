"""Builds the Part 4.1/4.2 section of reports/hw10/METRICS.md from raw/spans_traces.jsonl and raw/part4_trace_ids.json (no numbers typed by hand)."""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[2] / "reports" / "hw10"
ids = json.load(open(root / "raw" / "part4_trace_ids.json", encoding="utf-8"))
spans = [json.loads(x) for x in open(root / "raw" / ("spans_traces.jsonl"), encoding="utf-8") if x.strip()]


def table(tid):
    rows = sorted((s for s in spans if s["trace_id"] == tid), key=lambda s: (s["start_ms"], -s["duration_ms"]))
    out = ["| # | stage | start | end | duration (ms) | status | error / details |", "|---|---|---|---|---|---|---|"]
    for i, s in enumerate(rows, 1):
        det = s["error"] or ", ".join(f"{k}={v}" for k, v in s["attrs"].items() if v is not None and k in ("path", "similarity", "attempts", "stored", "pipeline_status"))
        out.append(f"| {i} | {s['stage']} | {s['start'][11:]} | {s['end'][11:]} | {s['duration_ms']:,.1f} | {s['status']} | {det} |")
    return "\n".join(out), rows


m, mr = table(ids["cache_miss_success"]["trace_id"])
h, hr = table(ids["cache_hit"]["trace_id"])
f, fr = table(ids["failed"]["trace_id"])
fail = ids["failed"]
text = f"""## Part 4.1 / 4.2 - Trace propagation and the three required traces

One identifier per request: the `trace_id` of every span is the HW8 `correlation_id` (the same value is in the Kafka messages), so nothing is joined afterwards. Each stage writes one JSON span with
trace_id, stage, start, end, status and error (`code/kafka_hw8/tracing.py`; the spans of all three traces are in `raw/spans_traces.jsonl`). `queue_*` spans are the time a message waited in a
topic before the next stage took it (from the Kafka message timestamp); `final` is the ingress receiving the Reviewer's answer; `request` is the whole request.

### Cache MISS, successful - trace_id {ids['cache_miss_success']['trace_id']}
Question: {ids['cache_miss_success']['question']}

{m}

### Cache HIT - trace_id {ids['cache_hit']['trace_id']}
Question: {ids['cache_hit']['question']} (the same question asked again)

{h}

### FAILED - trace_id {fail['trace_id']}
Question: {fail['question']}. The Writer process was replaced by one whose model endpoint was unreachable (OLLAMA_HOST pointed at a closed port), so a real failure was produced rather than a simulated one.

{f}

What this shows: the hit trace has only `cache_lookup` (path=hit, {next(s for s in hr if s['stage'] == 'cache_lookup')['duration_ms']:,.1f} ms) and the `request` span; no Kafka stage runs. The miss trace has every stage in order
(cache_lookup, facts_lookup, inbox, planner, writer, reviewer, final, cache_store) with {sum(1 for s in mr if s['stage'].startswith('queue_'))} queue-wait spans between the agents. In the failed trace the failing stage is **{fail['failing_stage']}**:
three attempts, error `{fail['error']}`, after which the message was dead-lettered; the ingress then found no answer on the final topic within 45 s, so `final` and `request` carry the status error too, and nothing was cached.
The trace identifies where it failed (writer) and the symptom the caller saw (no answer), which the single `request` span would not.
"""
out = root / "METRICS.md"
prev = out.read_text(encoding="utf-8")
parts = prev.split("\n## ")
keep = [parts[0]] + [x for x in parts[1:] if not x.startswith("Part 4.1 ")]
out.write_text("\n## ".join(keep).rstrip() + "\n\n" + text, encoding="utf-8")
print(text)
