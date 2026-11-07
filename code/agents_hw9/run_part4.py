"""
DATA-260 Homework 9 - Part 4: develop -> validate -> final test -> demonstrations. Real qwen3:8b answers, real MySQL facts, reference-data Evaluator.

  train     baseline run over training_data.json; first-answer failures that repeat become candidate lessons (lessons_candidates.json),
            plus ONE deliberately over-broad CONTROLLED candidate, to show the validation gate rejecting a harmful lesson
  validate  each candidate is added in turn to the current kept set and the validation set is run before/after (one attempt per question,
            so the lesson's effect on the first answer is measured, not hidden by the repair loop); kept only if
            (a) no previously correct answer becomes wrong, (b) at least one failing case is fixed, (c) failures do not increase,
            (d) unsupported answers do not increase  -> lessons.json
  test      test_data.json, once per variant (baseline / evaluator repair / lesson memory / validated improvement)
  demo      one complete revision sequence (controlled incomplete first answer) and one later question reusing a stored lesson
test_data.json is read only by the `test` stage and never to create lessons.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from agents import AnsweringAgent, EvaluatorAgent, LessonStore, propose_lessons  # noqa: E402
from system import make_variant, run_question  # noqa: E402

ROOT = HERE.parents[1]
DATA = HERE / "data"
VARIANTS = ["baseline", "evaluator_repair", "lesson_memory", "validated"]
CONTROLLED = {"failure_type": "CONTROLLED_OVERBROAD", "failure_pattern": "(controlled test) Multi-part questions produce long answers.",
              "correction": "If the question asks about more than one thing, answer only the first item and say the rest cannot be confirmed.",
              "applies_when": ["multi_part"], "source": "controlled: deliberately harmful, to demonstrate the validation gate"}


def load(name):
    return json.loads((DATA / f"{name}_data.json").read_text(encoding="utf-8"))


def run_set(items, variant, lessons, evaluator, label):
    agent, use_feedback = make_variant(variant, lessons)
    out = []
    for it in items:
        r = run_question(it["question"], agent, evaluator, use_feedback)
        r["id"] = it["id"]
        out.append(r)
        print(f'  [{label}] {it["id"]} attempts={r["n_attempts"]} final={r["final_result"]:6} {r["latency_ms"]:8.1f} ms  {r["failure_type"] or ""}', flush=True)
    return out, agent


def summary(results):
    n = len(results)
    ok = sum(r["final_result"] == "PASS" for r in results)
    return {"questions": n, "correct": ok, "incorrect": n - ok, "avg_attempts": round(statistics.mean(r["n_attempts"] for r in results), 2),
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 1)}


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2), encoding="utf-8")


def stage_train(a, ev):
    print("== training run (baseline, no lessons) ==")
    res, _ = run_set(load("training"), "baseline", None, ev, "train")
    failures = [{"id": r["id"], "failure_type": r["failure_type"]} for r in res if r["final_result"] != "PASS"]
    store = LessonStore(a.lessons_dir / "lessons_candidates.json", lessons=[])
    created = propose_lessons(failures, store)
    c = dict(CONTROLLED)
    store.add(c.pop("failure_type"), c["failure_pattern"], c["correction"], c["applies_when"], c["source"])
    store.save()
    dump(a.raw_dir / "part4_training_run.json", {"run_at": datetime.now().isoformat(timespec="seconds"), "summary": summary(res), "failures": failures,
                                                  "lessons_proposed": [ls["lesson_id"] for ls in created], "controlled_lesson": store.lessons[-1]["lesson_id"], "results": res})
    print(f'training: {summary(res)["correct"]}/{len(res)} correct, failures={[(f["id"], f["failure_type"]) for f in failures]}')
    print("candidate lessons:", [(ls["lesson_id"], ls["failure_type"]) for ls in store.lessons])


def stage_validate(a, ev):
    cands = LessonStore(a.lessons_dir / "lessons_candidates.json")
    val = load("validation")
    kept = LessonStore(a.lessons_dir / "lessons.json", lessons=[])
    print("== validation (single attempt, so a lesson's effect is not hidden by the repair loop): system without any lesson ==")
    before, _ = run_set(val, "lessons_only", kept, ev, "val-before")
    initial = before
    decisions = []
    for cand in cands.lessons:
        trial = kept.copy()
        trial.lessons.append(json.loads(json.dumps(cand)))
        print(f'== validation: add {cand["lesson_id"]} ({cand["failure_type"]}) ==')
        after, agent = run_set(val, "lessons_only", trial, ev, "val-after")
        b = {r["id"]: r for r in before}
        fixed = [r["id"] for r in after if b[r["id"]]["final_result"] != "PASS" and r["final_result"] == "PASS"]
        regress = [r["id"] for r in after if b[r["id"]]["final_result"] == "PASS" and r["final_result"] != "PASS"]
        fail_b, fail_a = sum(r["final_result"] != "PASS" for r in before), sum(r["final_result"] != "PASS" for r in after)
        unsup_b = sum(r["failure_type"] == "UNSUPPORTED_ANSWER" and r["final_result"] != "PASS" for r in before)
        unsup_a = sum(r["failure_type"] == "UNSUPPORTED_ANSWER" and r["final_result"] != "PASS" for r in after)
        checks = {"no previously correct answer became wrong": not regress, "at least one failing case fixed": bool(fixed),
                  "failures did not increase": fail_a <= fail_b, "unsupported answers did not increase": unsup_a <= unsup_b}
        keep = all(checks.values())
        decisions.append({"lesson_id": cand["lesson_id"], "failure_type": cand["failure_type"], "source": cand["source"], "kept": keep, "checks": checks,
                          "fixed": fixed, "regressions": regress, "failures_before": fail_b, "failures_after": fail_a,
                          "unsupported_before": unsup_b, "unsupported_after": unsup_a,
                          "correct_before": len(val) - fail_b, "correct_after": len(val) - fail_a, "results_after": after})
        print(f'   {"KEEP" if keep else "REJECT"} {cand["lesson_id"]}: fixed={fixed} regressions={regress} failures {fail_b}->{fail_a} unsupported {unsup_b}->{unsup_a}')
        if keep:
            clean = json.loads(json.dumps(cand))
            kept.lessons.append(clean)
            before = after
    kept.save()
    dump(a.raw_dir / "part4_validation.json", {"run_at": datetime.now().isoformat(timespec="seconds"), "validation_questions": len(val),
                                                 "baseline_summary": summary(initial), "results_without_lessons": initial,
                                                 "rule": "keep a lesson only if all four checks hold", "decisions": decisions,
                                                 "kept": [ls["lesson_id"] for ls in kept.lessons]})
    print("kept lessons:", [ls["lesson_id"] for ls in kept.lessons])


def stage_test(a, ev):
    cands, kept = LessonStore(a.lessons_dir / "lessons_candidates.json"), LessonStore(a.lessons_dir / "lessons.json")
    items = json.loads(Path(a.test_file).read_text(encoding="utf-8"))
    table, detail = {}, {}
    for v in VARIANTS:
        print(f"== final test: {v} ({len(items)} questions) ==")
        store = {"lesson_memory": cands, "validated": kept}.get(v)
        res, agent = run_set(items, v, store, ev, v[:6])
        table[v] = summary(res)
        detail[v] = {"results": res, "lessons_loaded": ({ls["lesson_id"]: ls["use_count"] for ls in agent.lessons.lessons} if agent.lessons else {})}
        print("  ", table[v])
    dump(a.raw_dir / "part4_test_results.json", {"run_at": datetime.now().isoformat(timespec="seconds"), "test_file": str(a.test_file), "model": "qwen3:8b (Ollama, thinking off, temperature 0, seed 9871)",
                                                 "lessons_used_by": {"lesson_memory": [ls["lesson_id"] for ls in cands.lessons], "validated": [ls["lesson_id"] for ls in kept.lessons]},
                                                 "table": table, "variants": detail})


def stage_demo(a, ev):
    kept = LessonStore(a.lessons_dir / "lessons.json")
    out = {"run_at": datetime.now().isoformat(timespec="seconds")}
    # 1. complete revision sequence with a controlled, deliberately incomplete first answer
    q = "For fixture FX-9871-00005, which team is the home team and what is its home ground?"
    first = "The home team is Sunnyvale Falcons."
    agent, fb = make_variant("evaluator_repair", None)
    out["revision"] = run_question(q, agent, ev, fb, forced_first_answer=first)
    print("== demo 1: revision sequence ==")
    print(json.dumps(out["revision"], indent=2))
    # 2. a later, unrelated question where a stored lesson is loaded and reused (use_count is persisted in lessons.json)
    q2 = "Who painted the Mona Lisa?"
    out["lesson_reuse"] = {"question": q2, "lessons_in_store": [{k: ls[k] for k in ("lesson_id", "failure_type", "created_at", "use_count", "source")} for ls in kept.lessons]}
    plain = AnsweringAgent(None)
    out["lesson_reuse"]["without_lessons"] = run_question(q2, plain, ev, use_feedback=False)
    agent = AnsweringAgent(kept)
    before = {ls["lesson_id"]: ls["use_count"] for ls in kept.lessons}
    out["lesson_reuse"]["with_lessons"] = run_question(q2, agent, ev, use_feedback=False)
    kept.save()
    out["lesson_reuse"]["use_count_before"], out["lesson_reuse"]["use_count_after"] = before, {ls["lesson_id"]: ls["use_count"] for ls in kept.lessons}
    out["lesson_reuse"]["persisted_in_file"] = {ls["lesson_id"]: ls["use_count"] for ls in LessonStore(a.lessons_dir / "lessons.json").lessons}
    print("== demo 2: lesson reuse ==")
    print(json.dumps(out["lesson_reuse"], indent=2))
    dump(a.raw_dir / "part4_demo.json", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all", "train", "validate", "test", "demo"], default="all")
    ap.add_argument("--raw-dir", default=str(ROOT / "reports" / "hw09" / "raw"))
    ap.add_argument("--lessons-dir", default=str(HERE))
    ap.add_argument("--test-file", default=str(DATA / "test_data.json"))
    a = ap.parse_args()
    a.raw_dir, a.lessons_dir = Path(a.raw_dir), Path(a.lessons_dir)
    ev = EvaluatorAgent()
    t0 = time.perf_counter()
    AnsweringAgent(None).answer({"question": "warm up: which league is this?", "attempt": 1, "feedback": None, "previous_answer": None})  # load qwen3, not counted
    for name, fn in (("train", stage_train), ("validate", stage_validate), ("test", stage_test), ("demo", stage_demo)):
        if a.stage in ("all", name):
            fn(a, ev)
    print(f"done in {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
