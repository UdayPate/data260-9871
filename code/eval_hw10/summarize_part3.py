"""Builds the Part 3 section of reports/hw10/METRICS.md from raw/part3_judge_scores.json (no numbers typed by hand)."""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[2] / "reports" / "hw10"
d = json.load(open(root / "raw" / "part3_judge_scores.json", encoding="utf-8"))
s, cs, j = d["statistics"], d["cases"], d["judge"]
cases = {c["case_id"]: c for c in json.load(open(root / "eval_cases.json", encoding="utf-8"))["cases"]}
rows = [f'| {c["case_id"]} | {cases[c["case_id"]]["question_plain"][:62]} | {c["human_label"]} | ' + " | ".join(str(x) for x in c["judge_scores"]) +
        f' | {c["judge_scores"][0] - c["human_label"]:+d} |' for c in cs]
over = [c["case_id"] for c in cs if c["human_label"] <= 2 and c["judge_scores"][0] >= 3]
under = [c["case_id"] for c in cs if c["human_label"] >= 4 and c["judge_scores"][0] <= 2]
low = [c for c in cs if c["human_label"] <= 2]
text = f"""## Part 3 - Validating the judge

Run at {d['run_at']} (local time). Judge: {d['criterion']}, local {j['model']}, temperature {j['temperature']}, seed {j['seed']}, thinking off, scale {j['scale']}.
The 20 drafts (`eval_cases.json`) and the human labels (`human_labels.csv`) were committed before this run; their SHA-256 (line endings normalised) are
{d['inputs']['eval_cases_sha256'][:16]}... and {d['inputs']['human_labels_sha256'][:16]}... in `raw/part3_judge_scores.json`. The judge ran 3 times on the same inputs and settings.

| case | question | human | judge run 1 | run 2 | run 3 | judge - human (run 1) |
|---|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

| Statistic | Value |
|---|---|
| Spearman rank correlation, human vs judge (run 1) | {s['spearman_rho_run1']} (p = {s['spearman_p_run1']}, n = {s['n_scored']}) |
| Mean absolute difference, human vs judge | {s['mean_abs_difference_per_run'][0]} / {s['mean_abs_difference_per_run'][1]} / {s['mean_abs_difference_per_run'][2]} (runs 1 / 2 / 3) |
| Mean judge score minus mean human label | {s['mean_judge_minus_mean_human_run1']:+} |
| Exact agreement / within 1 point (run 1) | {s['exact_agreement_run1_pct']}% / {s['within_1_run1_pct']}% |
| Cases whose score changed across the 3 runs | {s['cases_with_any_change_across_runs']} of {s['n_scored']} ({s['cases_with_any_change_pct']}%) |
| Run pairs where a score changed | {s['pairwise_changed']} of {s['pairwise_comparisons']} ({s['pairwise_changed_pct']}%) |
| Mean / maximum absolute change between runs | {s['mean_abs_change']} / {s['max_abs_change']} |

What this shows: the judge is perfectly repeatable but weakly valid. Its scores did not change in any of the {s['pairwise_comparisons']} run-to-run comparisons, which is expected with temperature 0 and a fixed seed, so this
measures determinism, not robustness: it says nothing about how the score moves if the wording of the draft or the prompt changes. Agreement with the human labels is weak: Spearman {s['spearman_rho_run1']}
(p = {s['spearman_p_run1']}, so not distinguishable from no correlation at n = {s['n_scored']}) and an average miss of {s['mean_abs_difference_run1']} points on a 5-point scale. The similar mean scores
(difference {s['mean_judge_minus_mean_human_run1']:+}) hide errors in both directions.

The errors are systematic. In {len(over)} of the {len(low)} drafts the human rated 1 or 2 ({', '.join(over)}), the judge rated 3 or higher: these are drafts that state a score, a phone number, a fee or a forecast that the system has no data for.
The judge's reasons say the draft "directly addresses the question", so it rewards answering over being supported. In the other direction, {len(under)} drafts the human rated 4 or 5 ({', '.join(under)}) got 2 or lower: the judge penalised
answers that correctly say the information does not exist or is not in the database.

Would I trust this judge to gate a deployment? No. A gate must catch unsupported answers, and this judge scores several invented answers higher than correct refusals. Evidence I would require first: (1) a Spearman correlation with human
labels clearly above chance on a larger set (at least 100 labelled drafts, ideally labelled by more than one person so human-human agreement is known); (2) a criterion that checks the draft against the supplied facts, so that unsupported answers
score low, then re-validated on the same labels; (3) a check of the judge under changes (paraphrased drafts, a different seed, a second judge model), since repeatability under a fixed seed is not robustness; (4) an agreed error budget,
for example at most one unsupported answer in 20 passed by the gate. The labels were written by one person on 20 cases, so these statistics are indicative only.
"""
out = root / "METRICS.md"
prev = out.read_text(encoding="utf-8")
parts = prev.split("\n## ")
keep = [parts[0]] + [p for p in parts[1:] if not p.startswith("Part 3 ")]
out.write_text("\n## ".join(keep).rstrip() + "\n\n" + text, encoding="utf-8")
print(text)
