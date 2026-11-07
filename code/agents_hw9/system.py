"""
DATA-260 Homework 9 - Part 4.1/4.4: the controller that runs one question through the agents, and the four system variants.

run_question(): attempt 1 -> Evaluator -> (REVISE and attempts left and use_feedback) attempt 2 with the feedback -> Evaluator -> stop.
At most two answer attempts; after the second the final result is reported whatever it is.

Variants (all use the same Answering Agent and Evaluator; they differ in what is switched on):
  baseline        1 attempt, no feedback, no lessons (the Evaluator only SCORES the answer afterwards)
  evaluator_repair  up to 2 attempts, the Evaluator's feedback drives the second attempt
  lesson_memory   evaluator_repair + every lesson that training proposed (lessons_candidates.json), loaded before answering
  validated       evaluator_repair + only the lessons kept by the validation gate (lessons.json)
  lessons_only    (validation gate only) 1 attempt + the given lessons: the effect of a lesson on the FIRST answer, not hidden by the repair loop
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agents import AnsweringAgent, EvaluatorAgent, LessonStore  # noqa: E402

MAX_ATTEMPTS = 2


def run_question(question: str, answering: AnsweringAgent, evaluator: EvaluatorAgent, use_feedback: bool, forced_first_answer: str | None = None) -> dict:
    t0 = time.perf_counter()
    attempts, feedback, previous = [], None, None
    for n in range(1, MAX_ATTEMPTS + 1):
        ans = answering.answer({"question": question, "attempt": n, "feedback": feedback, "previous_answer": previous}, forced_answer=forced_first_answer)
        ev = evaluator.evaluate({"question": question, "answer": ans["answer"]})
        attempts.append({"attempt": n, "answer": ans["answer"], "forced_for_test": ans["forced"], "lessons_used": ans["lessons_used"],
                         "answer_latency_ms": ans["latency_ms"], "evaluation": ev})
        if ev["result"] == "PASS" or not use_feedback or n == MAX_ATTEMPTS:
            break
        feedback, previous = ev["feedback"], ans["answer"]
    final = attempts[-1]
    return {"question": question, "attempts": attempts, "n_attempts": len(attempts), "final_answer": final["answer"],
            "final_result": final["evaluation"]["result"], "failure_type": final["evaluation"]["failure_type"],
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


def make_variant(name: str, lessons: LessonStore | None) -> tuple[AnsweringAgent, bool]:
    """-> (answering agent, use_feedback). `lessons` is used only by the two lesson variants (a private copy, so use_count never touches the files)."""
    if name == "baseline":
        return AnsweringAgent(None), False
    if name == "evaluator_repair":
        return AnsweringAgent(None), True
    if name in ("lesson_memory", "validated", "lessons_only"):
        return AnsweringAgent(lessons.copy() if lessons else LessonStore(lessons=[])), name != "lessons_only"
    raise ValueError(name)
