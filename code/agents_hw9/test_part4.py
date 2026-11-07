"""
DATA-260 Homework 9 - Part 4 smoke tests: real reference dataset, real MySQL fact lookup, scripted (fake) language model.
Checks the Evaluator verdicts on right/incomplete/wrong/unsupported answers, the two-attempt controller, lesson loading and the input files.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agents import AnsweringAgent, EvaluatorAgent, LessonStore  # noqa: E402
from system import make_variant, run_question  # noqa: E402

DATA = Path(__file__).parent / "data"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f'[{"PASS" if ok else "FAIL"}] {name}  {detail}')


class FakeModel:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def main() -> int:
    ev = EvaluatorAgent()
    ref = ev.ref
    c1, c2, c3 = list(ref)[:3]
    f1, f2 = ref[c1], ref[c2]
    # a team/ground that belongs to some OTHER fixture than c1, to build a wrong answer
    other_team = next(fx["home_team"] for c, fx in ref.items() if fx["home_team"] != f1["home_team"] and fx["home_team"] != f2["home_team"])
    q_team = f"Which team is the home team for fixture {c1}?"
    q_comp = f"For fixture {c1}, which team is the home team and what is its home ground?"
    q_spots = f"How many player spots are available for fixture {c1}?"
    q_two = f"What is the home ground of fixture {c1} and of fixture {c2}?"
    q_ghost = "Which team is the home team for fixture FX-9871-09999?"
    q_ref = f"Who is the referee for fixture {c1}?"
    q_unrel = "What is the capital of France?"

    def v(q, a):
        return ev.evaluate({"question": q, "answer": a})

    r = v(q_team, f"The home team is {f1['home_team']}.")
    check("correct simple answer -> PASS", r["result"] == "PASS", r["explanation"])
    r = v(q_comp, f"The home team is {f1['home_team']}.")
    check("compound answer missing the ground -> REVISE / OMITTED_FACT, feedback quotes the reference ground",
          r["result"] == "REVISE" and r["failure_type"] == "OMITTED_FACT" and f1["home_ground"].split(",")[0] in r["feedback"], r["feedback"])
    check("compound answer with both facts -> PASS", v(q_comp, f"{f1['home_team']} host at {f1['home_ground']}.")["result"] == "PASS")
    check("ground without the city is accepted", v(q_comp, f"{f1['home_team']} play at {f1['home_ground'].split(',')[0]}.")["result"] == "PASS")
    r = v(q_team, f"The home team is {other_team}.")
    check("another fixture's team -> REVISE / WRONG_FACT", r["result"] == "REVISE" and r["failure_type"] == "WRONG_FACT", r["feedback"])
    check("spots: right number -> PASS", v(q_spots, f"There are {f1['spots_available']} spots available for {c1}.")["result"] == "PASS")
    r = v(q_spots, f"There are {f1['spots_available'] + 3} spots available.")
    check("spots: wrong number -> REVISE", r["result"] == "REVISE", r["explanation"])
    check("spots: digits of the fixture code are not mistaken for the answer", v(q_spots, f"Fixture {c1} has no spots listed.")["result"] == "REVISE")
    check("two fixtures: both grounds -> PASS (the second fixture's ground is not 'foreign')",
          v(q_two, f"{c1}: {f1['home_ground']}; {c2}: {f2['home_ground']}.")["result"] == "PASS")
    r = v(q_two, f"{c1} is played at {f1['home_ground']}.")
    check("two fixtures: only one ground -> OMITTED_FACT", r["failure_type"] == "OMITTED_FACT", r["feedback"])
    check("unrelated question answered -> REVISE / UNSUPPORTED_ANSWER", (lambda r: r["result"] == "REVISE" and r["failure_type"] == "UNSUPPORTED_ANSWER")(v(q_unrel, "The capital of France is Paris.")))
    check("unrelated question politely declined -> PASS", v(q_unrel, "I can only help with league fixture questions, so I don't have that information.")["result"] == "PASS")
    check("unknown fixture with an invented team -> REVISE", v(q_ghost, f"The home team is {f1['home_team']}.")["failure_type"] == "UNSUPPORTED_ANSWER")
    check("unknown fixture reported as not found -> PASS", v(q_ghost, "That fixture does not exist in the league database.")["result"] == "PASS")
    check("unrecorded attribute invented -> REVISE", v(q_ref, "The referee is John Smith.")["result"] == "REVISE")
    check("unrecorded attribute declined -> PASS", v(q_ref, "The referee is not recorded for this fixture.")["result"] == "PASS")
    check("a refusal that still leaks a team name -> REVISE", v(q_ghost, f"I don't know, maybe {f1['home_team']}.")["result"] == "REVISE")

    # ---- controller: attempts, feedback, stopping
    wrong, right = f"The home team is {other_team}.", f"The home team is {f1['home_team']}."
    agent = AnsweringAgent(None, FakeModel([wrong, right]))
    t = run_question(q_team, agent, ev, use_feedback=True)
    second_prompt = agent.model.calls[1][1]["content"]
    check("repair: fails then passes -> 2 attempts, final PASS", t["n_attempts"] == 2 and t["final_result"] == "PASS", f'{t["n_attempts"]} attempts')
    check("repair: the second prompt carries the evaluator feedback and the previous answer", "evaluator rejected" in second_prompt and wrong in second_prompt)
    t = run_question(q_team, AnsweringAgent(None, FakeModel([wrong, wrong, right])), ev, use_feedback=True)
    check("stops after the second attempt even if still wrong", t["n_attempts"] == 2 and t["final_result"] == "REVISE")
    t = run_question(q_team, AnsweringAgent(None, FakeModel([wrong, right])), ev, use_feedback=False)
    check("baseline: one attempt only, no repair", t["n_attempts"] == 1 and t["final_result"] == "REVISE")
    t = run_question(q_team, AnsweringAgent(None, FakeModel([right])), ev, use_feedback=True)
    check("a first-attempt PASS stops at 1 attempt", t["n_attempts"] == 1 and t["final_result"] == "PASS")
    t = run_question(q_comp, AnsweringAgent(None, FakeModel([f"{f1['home_team']}, {f1['home_ground']}"])), ev, True, forced_first_answer=f"The home team is {f1['home_team']}.")
    check("controlled test: forced incomplete first answer is marked and repaired",
          t["attempts"][0]["forced_for_test"] and t["attempts"][0]["evaluation"]["result"] == "REVISE" and t["final_result"] == "PASS" and t["n_attempts"] == 2)

    # ---- lessons
    store = LessonStore(lessons=[])
    store.add("UNSUPPORTED_ANSWER", "pattern A", "CORRECTION-A", ["no_data"], "test")
    store.add("OMITTED_FACT", "pattern B", "CORRECTION-B", ["multi_part"], "test")
    fm = FakeModel([right])
    ag = AnsweringAgent(store, fm)
    ag.answer({"question": q_unrel, "attempt": 1, "feedback": None, "previous_answer": None})
    sys_prompt = fm.calls[0][0]["content"]
    check("a relevant lesson is loaded into the prompt and counted; an irrelevant one is not",
          "CORRECTION-A" in sys_prompt and "CORRECTION-B" not in sys_prompt and [ls["use_count"] for ls in store.lessons] == [1, 0], str([ls["use_count"] for ls in store.lessons]))
    check("lesson fields", set(store.lessons[0]) >= {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"})
    lo = make_variant("lessons_only", store)
    check("lessons_only variant (validation gate): lessons loaded, a single attempt", lo[0].lessons is not None and lo[1] is False)
    check("reference holds the whole fixtures table (FX-9871-00005 exists, FX-9871-09999 does not)", "FX-9871-00005" in ref and "FX-9871-09999" not in ref and len(ref) >= 5000, str(len(ref)))
    base, fb = make_variant("baseline", store), make_variant("evaluator_repair", store)
    check("baseline and repair variants load no lessons", base[0].lessons is None and fb[0].lessons is None and base[1] is False and fb[1] is True)
    check("lesson variants use a private copy (the store file is never mutated by a run)", make_variant("validated", store)[0].lessons is not store)

    # ---- input files
    files = {n: json.loads((DATA / f"{n}_data.json").read_text(encoding="utf-8")) for n in ("training", "validation", "test")}
    check("input files contain only id + question (no expected answers)", all(set(i) == {"id", "question"} for d in files.values() for i in d))
    qs = {n: {i["question"] for i in d} for n, d in files.items()}
    check("no question appears in two input files", not (qs["training"] & qs["validation"] or qs["training"] & qs["test"] or qs["validation"] & qs["test"]))
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
