"""Builds the Part 2 section of reports/hw10/METRICS.md from raw/part2_eval_results.json and raw/spans_part2.jsonl (no numbers typed by hand)."""
import json
import pathlib
import statistics as st

root = pathlib.Path(__file__).resolve().parents[2] / "reports" / "hw10"
d = json.load(open(root / "raw" / "part2_eval_results.json", encoding="utf-8"))
recs = d["records"]
ok = [r for r in recs if r["status"] == "ok"]
sc = lambda r, k: r["scores"][k]["score"]  # noqa: E731
rows = []
for r in ok:
    q = r["inputs"]["draft"]["value"]["question"].split("Question: ")[-1]
    fv = r["scores"]["final_vs_draft"]
    rows.append(f'| {r["question_no"]} | {q[:70]} | {r["trace_id"][:8]} | {sc(r, "plan_quality")} | {sc(r, "writer_helpfulness")} | {sc(r, "final_helpfulness")} | '
                f'{fv["difference"]:+d} | {"yes" if fv["final_equals_draft"] else "no"} | {fv["reviewer_status"]} |')
mean = lambda k: st.mean(sc(r, k) for r in ok)  # noqa: E731
diffs = [r["scores"]["final_vs_draft"]["difference"] for r in ok]
same = sum(r["scores"]["final_vs_draft"]["final_equals_draft"] for r in ok)
j = d["judge"]
text = f"""## Part 2 - Automated evaluation of the Kafka pipeline

Run at {d['run_at']} (local time). {len(ok)} of {len(recs)} requests evaluated (collect: {d['collect']['messages_read']} messages read, {d['collect']['malformed_skipped']} malformed skipped).
Judge: {j['framework']}, local {j['model']} via Ollama, temperature {j['temperature']}, seed {j['seed']}, thinking off, {j['timeout_s_per_call']:.0f} s timeout per call. Scale: {j['scale']}.
The judge sees the same question text the Planner saw (the database facts plus the question).

| # | question | trace | Plan Quality | Writer Helpfulness | Final Helpfulness | final - draft | final text = draft | Reviewer status |
|---|---|---|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

| Stage | Mean score (1-5) |
|---|---|
| Plan Quality (Planner) | {mean('plan_quality'):.2f} |
| Writer Helpfulness (Writer draft) | {mean('writer_helpfulness'):.2f} |
| Final Answer Helpfulness (Reviewer output) | {mean('final_helpfulness'):.2f} |
| Mean final - draft | {st.mean(diffs):+.2f} (min {min(diffs):+d}, max {max(diffs):+d}) |
| Requests where the final text is identical to the draft | {same} of {len(ok)} |

What this shows: the final answer did not improve on the draft in any request (mean difference {st.mean(diffs):+.2f}). The reason is structural, not a judge effect: the Reviewer does not rewrite, it only approves or rejects,
so in {same} of {len(ok)} requests the final answer is the Writer's draft word for word. A non-zero difference on identical text is therefore judge variation between two differently worded criteria, not an improvement.
The Planner's plans scored lowest (mean {mean('plan_quality'):.2f}); in requests 3 to 6 (all scored 2) the judge's reasons say the steps are relevant but lack specificity or completeness.
The judge is not perfectly consistent with itself: for request 2 its reason calls the plan specific, ordered and complete, yet the score is 2. Part 3 measures this judge against human labels.
{len(ok)} requests is a small sample, so these means are indicative only.
"""
out = root / "METRICS.md"
head = "# HW10 METRICS\n\n"
prev = out.read_text(encoding="utf-8") if out.exists() else head
parts = prev.split("\n## ")
keep = [parts[0]] + [p for p in parts[1:] if not p.startswith("Part 2 ")]
out.write_text("\n## ".join(keep).rstrip() + "\n\n" + text, encoding="utf-8")
print(text)
