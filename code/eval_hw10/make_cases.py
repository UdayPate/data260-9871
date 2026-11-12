"""
DATA-260 Homework 10 - Part 3.1: freeze the evaluation cases. Sends 20 questions through the REAL Planner -> Writer pipeline (qwen3:8b, over Kafka; no semantic
cache, so every question gets a fresh draft) and saves each Writer draft with its question and plan.

    code\\venv\\Scripts\\python.exe code/eval_hw10/make_cases.py

Writes reports/hw10/eval_cases.json (20 cases), a BLANK reports/hw10/human_labels.csv (case_id,human_label: filled in by hand) and reports/hw10/label_sheet.md
(the same cases laid out for reading while labelling). Refuses to overwrite an existing eval_cases.json or human_labels.csv: the cases are frozen once committed.

The 20 questions mix answerable fixture-fact questions (database facts are sent with the question, as in HW9), fixture codes that do not exist, general league
questions, and questions the system has no information to answer, so that the drafts are not all of one quality. Their order was fixed before any draft existed.
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "cache_hw9"), str(HERE.parent / "tracing_hw10"), str(HERE.parent / "kafka_hw8")]
import evaluator  # noqa: E402
import harness  # noqa: E402
from facts import lookup_facts  # noqa: E402
from pipeline_client import PipelineClient  # noqa: E402

OUT = HERE.parents[1] / "reports" / "hw10"
QUESTIONS = [
    "Which team is the home team for fixture FX-9871-00012?",
    "How many player spots are still open on fixture FX-9871-00031, and which teams are playing?",
    "Where will fixture FX-9871-00044 be played?",
    "Name both teams in fixture FX-9871-00057 and say which one is at home.",
    "Is there room for 3 more players to register for fixture FX-9871-00063?",
    "What is the name of fixture FX-9871-00078?",
    "Which team is the home team for fixture FX-9871-09101?",
    "How many player spots are open on fixture FX-9871-09102?",
    "What should a league office check before scheduling a Soccer fixture on a shared field?",
    "How should a league office handle a team that cannot field enough players on match day?",
    "Explain how a round-robin schedule works for a six-team volleyball league.",
    "What information belongs in a fixture cancellation notice sent to both teams?",
    "Why might a league cap the number of substitutions in a cricket match?",
    "What are three ways to reduce no-shows for early-morning basketball fixtures?",
    "How do you break a tie in league standings when two teams have the same points?",
    "What was the final score of last season's championship game?",
    "What is the phone number of the league office?",
    "Which referee is assigned to fixture FX-9871-00012?",
    "How much does it cost to register a team this season?",
    "Summarise the weather forecast for this Saturday's fixtures.",
]


def main() -> int:
    cases_path, labels_path, sheet_path = OUT / "eval_cases.json", OUT / "human_labels.csv", OUT / "label_sheet.md"
    if cases_path.exists() or labels_path.exists():
        sys.exit("eval_cases.json / human_labels.csv already exist: the cases are frozen. Delete them yourself if you really mean to start over.")
    log_dir = OUT / "raw"
    log_dir.mkdir(parents=True, exist_ok=True)
    procs, _ = harness.start_agents(log_dir, "part3_cases")
    pipeline = PipelineClient()
    ids = []
    try:
        print("warm-up ...", flush=True)
        pipeline.ask("Warm-up question: name one team sport.")
        for i, q in enumerate(QUESTIONS, 1):
            full = lookup_facts(q)["block"] + "Question: " + q
            tid = str(uuid.uuid4())
            r = pipeline.ask(full, trace_id=tid)
            ids.append(tid)
            print(f"case_{i:02d} reviewer={r['status']}  {q}", flush=True)
    finally:
        pipeline.close()
        for p in procs.values():
            harness.kill(p)
    bundles, stats = evaluator.collect(set(ids), timeout_s=60)
    print("collect:", stats)
    cases = []
    for i, (q, tid) in enumerate(zip(QUESTIONS, ids, strict=True), 1):
        b = bundles[tid]
        if "draft" not in b or "plan" not in b:
            sys.exit(f"case_{i:02d}: no draft/plan collected - nothing written")
        cases.append({"case_id": f"case_{i:02d}", "trace_id": tid, "question": b["draft"]["value"]["question"], "question_plain": q,
                      "plan": b["plan"]["value"]["plan"], "draft": b["draft"]["value"]["draft"],
                      "reviewer_status": b["final"]["value"]["status"] if "final" in b else None,
                      "draft_message": {k: b["draft"][k] for k in ("topic", "partition", "offset", "timestamp_ms")}})
    doc = {"created_at": datetime.now().isoformat(timespec="seconds"), "source": "HW8 pipeline Planner -> Writer, qwen3:8b, SEED 9871, no semantic cache",
           "n": len(cases), "cases": cases}
    cases_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    labels_path.write_text("case_id,human_label\n" + "".join(f"{c['case_id']},\n" for c in cases), encoding="utf-8")
    sheet = ["# HW10 labelling sheet", "",
             "Give each draft ONE helpfulness label, 1-5, by hand: 1 = very poor (wrong, evasive or off-topic), 2 = poor, 3 = adequate, 4 = good, 5 = excellent (accurate, relevant, useful).",
             "Judge the DRAFT against the question and the facts that were supplied with it. Write the labels in human_labels.csv. Do not use an LLM, and do not change a label after you have seen judge scores.", ""]
    for c in cases:
        sheet += [f"## {c['case_id']}", "", "**Question sent to the pipeline:**", "", "```", c["question"], "```", "", "**Writer draft:**", "", "```", c["draft"], "```", ""]
    sheet_path.write_text("\n".join(sheet), encoding="utf-8")
    print(f"wrote {cases_path.name}, {labels_path.name} (blank), {sheet_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
