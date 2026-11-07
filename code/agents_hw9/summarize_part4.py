"""Builds the Part 4 section of reports/hw09/METRICS.md from raw/part4_*.json and lessons.json. No number is typed by hand."""

import json
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
RAW = ROOT / "reports" / "hw09" / "raw"
NAMES = {"baseline": "Baseline", "evaluator_repair": "Evaluator Repair", "lesson_memory": "Lesson Memory", "validated": "Validated Improvement"}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main() -> None:
    tr, va, te, dm = (jl(RAW / f"part4_{n}.json") for n in ("training_run", "validation", "test_results", "demo"))
    kept, cands = jl(HERE / "lessons.json"), jl(HERE / "lessons_candidates.json")
    test_q = {i["id"]: i["question"] for i in jl(HERE / "data" / "test_data.json")}
    n_test = te["table"]["baseline"]["questions"]

    tbl = ["| Variant | Correct answers | Incorrect answers | Average attempts | Average latency (ms) |", "|---|---|---|---|---|"]
    for k, name in NAMES.items():
        t = te["table"][k]
        tbl.append(f'| {name} | {t["correct"]} / {t["questions"]} | {t["incorrect"]} | {t["avg_attempts"]} | {t["avg_latency_ms"]} |')

    first_fail = {}
    for k in NAMES:
        first_fail[k] = [(r["id"], r["attempts"][0]["evaluation"]["failure_type"], r["attempts"][0]["answer"]) for r in te["variants"][k]["results"]
                         if r["attempts"][0]["evaluation"]["result"] != "PASS"]
    ff = ["| Variant | Questions whose FIRST answer failed | Failure type |", "|---|---|---|"]
    for k, name in NAMES.items():
        items = first_fail[k]
        ff.append(f'| {name} | {", ".join(i[0] for i in items) or "none"} | {", ".join(sorted({i[1] for i in items})) or "-"} |')

    dec = ["| Candidate lesson | Source | Fixed | Regressions | Failures before -> after | Unsupported before -> after | Decision |", "|---|---|---|---|---|---|---|"]
    for d in va["decisions"]:
        dec.append(f'| {d["lesson_id"]} ({d["failure_type"]}) | {d["source"]} | {", ".join(d["fixed"]) or "none"} | {", ".join(d["regressions"]) or "none"} | '
                   f'{d["failures_before"]} -> {d["failures_after"]} | {d["unsupported_before"]} -> {d["unsupported_after"]} | **{"KEEP" if d["kept"] else "REJECT"}** |')
    rejected = [d for d in va["decisions"] if not d["kept"]]
    rej = rejected[0] if rejected else None
    rej_case = next(r for r in rej["results_after"] if r["id"] == rej["regressions"][0]) if rej and rej["regressions"] else None

    memory_extra = [r for r in te["variants"]["lesson_memory"]["results"] if r["n_attempts"] > 1]
    ctrl_id = tr["controlled_lesson"]
    assert all(ctrl_id in r["attempts"][0]["lessons_used"] for r in memory_extra), "prose assumes the extra attempts happened with the controlled lesson loaded"
    base_fail_q = "; ".join(f'"{test_q[i[0]]}"' for i in first_fail["baseline"])
    rv, lr = dm["revision"], dm["lesson_reuse"]
    lat_b, lat_v = te["table"]["baseline"]["avg_latency_ms"], te["table"]["validated"]["avg_latency_ms"]
    text = f"""
## Part 4 - Self-improving multi-agent system

Model: {te['model']}. Run at {te['run_at']} (local time). Input files: {n_test} test, {va['validation_questions']} validation and
{tr['summary']['questions']} training questions (`code/agents_hw9/data/`, questions only; the reference dataset holds all fixtures of `s9871_rel`).
The Evaluator is rule-based and reads only the reference dataset; the Answering Agent reads the same facts from MySQL and never sees the reference file.

### 4.4 Final test (test_data.json, each variant run once on the same {n_test} questions)

""" + "\n".join(tbl) + """

A question counts as correct when the Evaluator's final verdict is PASS. First-answer failures per variant:

""" + "\n".join(ff) + f"""

What this shows: without feedback the baseline gets {te['table']['baseline']['correct']} of {n_test} right; its {te['table']['baseline']['incorrect']} errors are all the same kind: off-topic questions ({base_fail_q})
answered from general knowledge instead of saying the data is not available. The Evaluator's feedback repaired all of them on the second attempt
(Evaluator Repair {te['table']['evaluator_repair']['correct']}/{n_test}), at the cost of {te['table']['evaluator_repair']['avg_attempts']} attempts per question on average. The validated lesson lets the first answer be right
(Validated Improvement {te['table']['validated']['correct']}/{n_test}, average attempts {te['table']['validated']['avg_attempts']}). Lesson Memory, which loads every proposed lesson without validation, also ends with
{te['table']['lesson_memory']['correct']}/{n_test} correct but needed {te['table']['lesson_memory']['avg_attempts']} attempts, because it also loaded the harmful controlled lesson ({ctrl_id}, which was loaded on {', '.join(r['id'] for r in memory_extra)}; those needed a second attempt:
the Evaluator caught the omitted part and the repair loop fixed it, so the damage shows up as extra attempts and latency, not as a wrong final answer).
Average latency is nearly the same for Baseline and Evaluator Repair ({lat_b} and {te['table']['evaluator_repair']['avg_latency_ms']} ms); the lower figure for Validated Improvement ({lat_v} ms) is mostly because the
refusals it now gives are very short answers, not a speed-up of the model. With {n_test} questions, a one-question difference is not strong evidence; qwen3 is not bit-reproducible, so another run can differ slightly.

### 4.1 Complete revision sequence (controlled test: the first answer is deliberately incomplete)

- Question: {rv['question']}
- Attempt 1 (forced for the test): {rv['attempts'][0]['answer']}
- Evaluator: {rv['attempts'][0]['evaluation']['result']} - {rv['attempts'][0]['evaluation']['explanation']}
- Feedback: {rv['attempts'][0]['evaluation']['feedback']}
- Attempt 2 (revised by the Answering Agent): {rv['attempts'][1]['answer']}
- Evaluator: {rv['attempts'][1]['evaluation']['result']} - {rv['attempts'][1]['evaluation']['explanation']}
- Attempts: {rv['n_attempts']} (maximum 2). Final answer / result: {rv['final_answer']} / {rv['final_result']}

### 4.2 Lessons and reuse

Training ({tr['summary']['correct']}/{tr['summary']['questions']} correct on the first attempt) failed on {', '.join(f['id'] for f in tr['failures'])} - the same pattern ({tr['failures'][0]['failure_type']}) twice, so the Evaluator
proposed one lesson from it. A second candidate was added on purpose as a controlled test of the validation gate.

Kept lesson store (`code/agents_hw9/lessons.json`, use_count after the demonstration):

```json
{json.dumps(kept, indent=2)}
```

Reuse demonstration, later question "{lr['question']}": without lessons the answer was "{lr['without_lessons']['final_answer']}" ({lr['without_lessons']['final_result']}, {lr['without_lessons']['failure_type']}); with the store loaded
(lessons used: {', '.join(lr['with_lessons']['attempts'][0]['lessons_used'])}) it was "{lr['with_lessons']['final_answer']}" ({lr['with_lessons']['final_result']}). use_count went {json.dumps(lr['use_count_before'])} -> {json.dumps(lr['use_count_after'])}
and the new value is in the file ({json.dumps(lr['persisted_in_file'])}).

### 4.3 Validation (validation_data.json, one attempt per question so the lesson's own effect is measured)

Keep a lesson only if: no previously correct answer becomes wrong; at least one failing case is fixed; total failures do not increase; unsupported answers do not increase.

""" + "\n".join(dec) + """

""" + (f"""The rejected lesson ("{rej['source']}") told the agent to answer only the first part of a multi-part question. On {rej['regressions'][0]} it changed a previously correct answer into
a {rej_case['failure_type']} ({rej_case['final_answer']!r}), so it was removed, as the assignment requires. Candidates: {len(cands)}; kept: {len(kept)}. test_data.json was not used to create or choose any lesson.
""" if rej_case else "No candidate was rejected on this run.\n") + """
### Short explanations

- Agent communication: the controller passes plain JSON messages. To the Answering Agent: question, attempt number, and (on attempt 2) the Evaluator's feedback and its previous answer. From it: the answer and the lessons it used.
  To the Evaluator Agent: question and answer. From it: PASS or REVISE, an explanation, feedback and a failure type. The agents never share state other than these messages.
- Lesson reuse: before each answer the Answering Agent computes tags for the question (multi-part, no recorded data, names a fixture), loads the lessons whose `applies_when` matches, adds their corrections to its prompt and increments `use_count`.
- Stopping condition: at most two attempts. A PASS stops immediately; a REVISE after attempt 1 triggers one revision; after attempt 2 the system stops and reports the result whatever it is.
- Validation process: each candidate is added to the kept set, the validation questions are run before and after, and the four rules above decide. The test set is run only afterwards, once per variant.
- Limitation: the Evaluator recognises what a question asks with keyword patterns and checks the answer by string matching, so an unusual phrasing or a differently worded correct answer can be mis-scored; only {n} test questions were used, and
  the failures are concentrated in one pattern (answering off-topic questions), so the results do not show how the lessons would behave on other kinds of failure.
""".replace("{n}", str(n_test))
    p = ROOT / "reports" / "hw09" / "METRICS.md"
    cur = p.read_text(encoding="utf-8")
    cur = cur.split("\n## Part 4 - ")[0].rstrip() + "\n"
    p.write_text(cur + text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
