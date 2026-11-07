"""
DATA-260 Homework 9 - Part 4: the Answering Agent, the Evaluator Agent and the lesson store.

Agents talk by plain JSON messages (dicts), passed by the controller in system.py:
  controller -> Answering Agent : {"question", "attempt", "feedback" (None on attempt 1), "previous_answer"}
  Answering Agent -> controller : {"answer", "attempt", "lessons_used": [ids], "latency_ms"}
  controller -> Evaluator Agent : {"question", "answer"}
  Evaluator Agent -> controller : {"result": "PASS"|"REVISE", "explanation", "feedback", "failure_type", "missing": [...]}

AnsweringAgent  qwen3:8b (Ollama, via src/model_client.ModelClient, thinking off, temperature 0, SEED 9871). It is given the league
                facts for the fixture codes in the question, read from MySQL s9871_rel (reuse: cache_hw9/facts.py), plus the lessons that
                apply to the question. It never sees the reference dataset.
EvaluatorAgent  rule based. Its ground truth is ONLY data/reference_dataset.json (a JSON export of the same tables, a separate source), so
                the verdict is reproducible and cannot be talked into a PASS. It decides what the question requires with qa_rules,
                checks the answer for those facts, and writes feedback that quotes the reference values.
LessonStore     lessons.json: {lesson_id, failure_pattern, correction, created_at, use_count} (+ failure_type, applies_when, source).
"""

import contextlib
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cache_hw9"))
sys.path.insert(0, str(ROOT))
from facts import lookup_facts  # noqa: E402
from qa_rules import asks_unrecorded, attributes_asked, fixture_codes  # noqa: E402
from src.model_client import ModelClient  # noqa: E402

SEED = 9871
REFERENCE_PATH = HERE / "data" / "reference_dataset.json"
REFUSAL = re.compile(r"\b(?:don't|do not|doesn't|does not|cannot|can't|unable|not able|isn't|is not|no (?:such|information|record|data)|"
                     r"not (?:available|provided|listed|recorded|found|included)|outside|only (?:help|answer|assist)|sorry)\b", re.IGNORECASE)


# ----------------------------------------------------------------------------------------------------------- lessons
class LessonStore:
    def __init__(self, path: Path | None = None, lessons: list[dict] | None = None):
        self.path = Path(path) if path else None
        self.lessons = list(lessons) if lessons is not None else (json.loads(self.path.read_text(encoding="utf-8")) if self.path and self.path.exists() else [])

    def save(self, path: Path | None = None) -> None:
        (Path(path) if path else self.path).write_text(json.dumps(self.lessons, indent=2), encoding="utf-8")

    def next_id(self) -> str:
        return f"lesson_{len(self.lessons) + 1:03d}"

    def add(self, failure_type: str, failure_pattern: str, correction: str, applies_when: list[str], source: str, lesson_id: str | None = None) -> dict:
        lesson = {"lesson_id": lesson_id or self.next_id(), "failure_pattern": failure_pattern, "correction": correction,
                  "created_at": date.today().isoformat(), "use_count": 0, "failure_type": failure_type, "applies_when": applies_when, "source": source}
        self.lessons.append(lesson)
        return lesson

    def relevant(self, tags: set[str]) -> list[dict]:
        return [ls for ls in self.lessons if set(ls["applies_when"]) & tags]

    def copy(self) -> "LessonStore":
        return LessonStore(lessons=json.loads(json.dumps(self.lessons)))


# -------------------------------------------------------------------------------------------------- Answering Agent
def question_tags(question: str, facts: dict) -> set[str]:
    """Features of the QUESTION (not of any answer) that decide which lessons are relevant."""
    tags = set()
    attrs, codes = attributes_asked(question), fixture_codes(question)
    if len(attrs) >= 2 or len(codes) >= 2:
        tags.add("multi_part")
    if not codes or asks_unrecorded(question) or any(facts["facts"].get(c) is None for c in codes):
        tags.add("no_data")
    if codes:
        tags.add("fixture")
    return tags


SYSTEM = ("You are the fixture assistant for a community sports league. Answer the user's question using the league facts given with it. "
          "Reply in one short sentence.")


class AnsweringAgent:
    def __init__(self, lessons: LessonStore | None = None, model: ModelClient | None = None):
        self.lessons = lessons
        self.model = model or ModelClient(temperature=0, reasoning=False, seed=SEED)

    def answer(self, msg: dict, forced_answer: str | None = None) -> dict:
        """msg = {"question", "attempt", "feedback", "previous_answer"}. forced_answer is the controlled-test hook: it replaces the model's
        first attempt with a given (deliberately incomplete or wrong) answer so the repair workflow can be shown reliably."""
        import time
        t0 = time.perf_counter()
        facts = lookup_facts(msg["question"])
        used = []
        system = SYSTEM
        if self.lessons is not None:
            used = self.lessons.relevant(question_tags(msg["question"], facts))
            if used:
                system += "\n\nLessons learned from earlier mistakes - follow them:\n" + "\n".join(f"- {ls['correction']}" for ls in used)
                for ls in used:
                    ls["use_count"] += 1
        user = facts["block"] + "Question: " + msg["question"]
        if msg.get("feedback"):
            user += (f"\n\nYour previous answer was:\n{msg['previous_answer']}\n\nThe evaluator rejected it with this feedback:\n{msg['feedback']}\n"
                     "Write a corrected answer (one short sentence).")
        if forced_answer is not None and msg["attempt"] == 1:
            text = forced_answer
        else:
            with contextlib.redirect_stdout(io.StringIO()):  # ModelClient prints token counts on every turn
                text = self.model.complete([{"role": "system", "content": system}, {"role": "user", "content": user}])
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return {"answer": text, "attempt": msg["attempt"], "lessons_used": [ls["lesson_id"] for ls in used],
                "forced": forced_answer is not None and msg["attempt"] == 1, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


# --------------------------------------------------------------------------------------------------- Evaluator Agent
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("’", "'")).strip()


def values_for(fx: dict, attr: str) -> list[str]:
    """The reference strings an answer must contain for one attribute of one fixture."""
    if attr == "home_team":
        return [fx["home_team"]]
    if attr == "home_ground":
        return [fx["home_ground"].split(",")[0].strip()]  # the park/field name; the city after the comma is optional
    if attr == "teams":
        return [t.strip() for t in fx["teams_players"].split(" vs ")]
    if attr == "spots":
        return [str(fx["spots_available"])]
    if attr == "fixture_name":
        return [fx["fixture_name"].split(" (")[0]]
    raise ValueError(attr)


class EvaluatorAgent:
    def __init__(self, reference_path: Path = REFERENCE_PATH):
        self.ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))["fixtures"]
        self.all_values = {attr: {_norm(v) for fx in self.ref.values() for v in values_for(fx, attr)}
                           for attr in ("home_team", "home_ground", "teams", "spots", "fixture_name")}
        self.team_and_ground_values = self.all_values["home_team"] | self.all_values["home_ground"]

    def _foreign_values(self, attr: str, codes: list[str]) -> set[str]:
        own = {_norm(v) for c in codes for v in values_for(self.ref[c], attr)}
        # a value of another fixture only counts as foreign if it is not just a piece of one of this fixture's own values
        return {v for v in self.all_values[attr] if v not in own and not any(v in o for o in own)}

    def evaluate(self, msg: dict) -> dict:
        question, answer = msg["question"], msg["answer"]
        a = _norm(answer)
        codes = fixture_codes(question)
        unknown = [c for c in codes if c not in self.ref]
        refuses = bool(REFUSAL.search(answer))
        # --- questions the reference cannot answer: unrelated, unknown fixture, or something the database does not record
        if not codes or unknown or asks_unrecorded(question):
            why = ("is not about league fixtures" if not codes else f"names fixture(s) {', '.join(unknown)} that are not in the reference data"
                   if unknown else "asks for something the league data does not record")
            leaked = [v for v in self.team_and_ground_values if v in a]
            if refuses and not leaked:
                return self._verdict("PASS", f"The question {why}, and the answer correctly says the information is not available.")
            return self._verdict("REVISE", f"The question {why}, but the answer gives an unsupported answer.",
                                 "The reference data has no answer to this question. Say that you do not have that information; do not answer from "
                                 "general knowledge and do not state any team or ground.", "UNSUPPORTED_ANSWER")
        # --- known fixtures: every requested fact must be present and correct
        attrs = attributes_asked(question)
        missing, wrong = [], []
        stripped = re.sub(r"FX-9871-\d{5}|#\d+", "", answer)
        numbers = set(re.findall(r"(?<![\w-])\d+(?![\w-])", stripped))
        for c in codes:
            for attr in attrs:
                for v in values_for(self.ref[c], attr):
                    if (v not in numbers) if attr == "spots" else (_norm(v) not in a):
                        missing.append((c, attr, v))
        for attr in attrs:
            if attr == "spots":
                allowed = {str(self.ref[c]["spots_available"]) for c in codes}
                wrong += [(",".join(codes), attr, n) for n in sorted(numbers - allowed)]
            else:
                wrong += [(",".join(codes), attr, f) for f in sorted(self._foreign_values(attr, codes)) if f in a]
        if wrong:
            detail = "; ".join(f"{attr.replace('_', ' ')}: '{w}' is not the value for the fixture asked about" for _, attr, w in wrong)
            fb = "Wrong value(s): " + detail + ". Reference: " + self._reference_text(codes, attrs)
            return self._verdict("REVISE", "The answer contains a value that does not match the reference data.", fb, "WRONG_FACT", wrong)
        if missing:
            miss_txt = "; ".join(f"{c} {attr.replace('_', ' ')} ('{v}')" for c, attr, v in missing)
            return self._verdict("REVISE", "The answer leaves out requested information: " + ", ".join(sorted({m[1].replace('_', ' ') for m in missing})) + ".",
                                 "Your answer is missing: " + miss_txt + ". Answer every part of the question using the facts provided.", "OMITTED_FACT", missing)
        return self._verdict("PASS", "Every requested fact matches the reference data.")

    def _reference_text(self, codes, attrs) -> str:
        return "; ".join(f"{c}: " + ", ".join(f"{attr.replace('_', ' ')} = {' / '.join(values_for(self.ref[c], attr))}" for attr in attrs) for c in codes)

    @staticmethod
    def _verdict(result, explanation, feedback=None, failure_type=None, detail=None) -> dict:
        return {"result": result, "explanation": explanation, "feedback": feedback, "failure_type": failure_type,
                "missing_or_wrong": [list(d) for d in (detail or [])]}


# ------------------------------------------------------------------------------------------------ lesson proposals
LESSON_TEMPLATES = {  # failure_type -> (failure_pattern, correction, applies_when)
    "OMITTED_FACT": ("The answer leaves out part of what the question asked (for example the home ground, or the number of spots).",
                     "Before answering, list every item the question asks for and make sure the answer states each one, using the facts provided.",
                     ["multi_part"]),
    "UNSUPPORTED_ANSWER": ("The answer states something the league facts do not support (unknown fixture, data the league does not record, or a question that is not about the league).",
                           "If the provided facts do not contain what is asked, reply that you do not have that information; do not answer from general knowledge and do not guess.",
                           ["no_data"]),
    "WRONG_FACT": ("The answer gives a value that belongs to a different fixture or is not in the facts.",
                   "Copy every value exactly from the facts provided for the fixture asked about; never mix in values from other fixtures.",
                   ["fixture"]),
}
MIN_REPEATS = 2  # a failure pattern must be seen at least this many times in the training data before it becomes a lesson


def propose_lessons(failures: list[dict], store: LessonStore) -> list[dict]:
    """failures = training results whose first answer failed. One lesson per failure type that repeats MIN_REPEATS+ times."""
    counts = {}
    for f in failures:
        counts.setdefault(f["failure_type"], []).append(f["id"])
    created = []
    for ftype, ids in sorted(counts.items()):
        if len(ids) >= MIN_REPEATS and ftype in LESSON_TEMPLATES:
            pattern, correction, applies = LESSON_TEMPLATES[ftype]
            created.append(store.add(ftype, pattern, correction, applies, source="training failures: " + ", ".join(ids)))
    return created
