"""
DATA-260 Homework 10 - the judge: DeepEval GEval criteria scored by a LOCAL model (qwen3:8b through Ollama), on a 1-5 scale.

Judge settings (documented in the report, identical for every run): model qwen3:8b, temperature 0, seed 9871, thinking off, JSON-schema constrained
replies, a hard per-call timeout (JUDGE_TIMEOUT_S) so an unavailable model cannot hang the run.

Scale: GEval asks the judge for an integer 0-10 against a rubric of five bands and divides by 10. The rubric bands are 0-2, 3-4, 5-6, 7-8, 9-10, which are
read back as 1, 2, 3, 4, 5 (1 = very poor, 5 = excellent). GEval's 0-1 value is kept too, as `raw`.
"""

import os
import time

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import GEval  # noqa: E402
from deepeval.metrics.g_eval.utils import Rubric  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

JUDGE_MODEL = "qwen3:8b"
JUDGE_TEMPERATURE = 0
JUDGE_SEED = 9871
JUDGE_TIMEOUT_S = float(os.environ.get("JUDGE_TIMEOUT_S", "120"))
SCALE = "1 (very poor) to 5 (excellent)"
BANDS = [((0, 2), "1 - very poor"), ((3, 4), "2 - poor"), ((5, 6), "3 - adequate"), ((7, 8), "4 - good"), ((9, 10), "5 - excellent")]


class JudgeUnavailable(RuntimeError):
    """The local judge model did not answer in time or at all."""


class LocalJudge(DeepEvalBaseLLM):
    def __init__(self, model: str = JUDGE_MODEL, timeout_s: float = JUDGE_TIMEOUT_S, host: str | None = None):
        import ollama
        self.model_name, self.timeout_s = model, timeout_s
        self.client = ollama.Client(host=host, timeout=timeout_s)
        super().__init__(model)

    def load_model(self):
        return self.client

    def generate(self, prompt: str, schema=None):
        try:
            reply = self.client.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}], think=False,
                                     format=schema.model_json_schema() if schema else None,
                                     options={"temperature": JUDGE_TEMPERATURE, "seed": JUDGE_SEED})
        except Exception as exc:  # connection refused, timeout, model missing: all mean the judge cannot score
            raise JudgeUnavailable(f"{type(exc).__name__}: {exc}") from exc
        text = reply["message"]["content"]
        return schema.model_validate_json(text) if schema else text

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


def band_to_score(raw_0_1: float) -> int:
    """GEval's 0-1 value (judge's 0-10 integer / 10) -> the 1-5 scale via the rubric bands."""
    s = round(raw_0_1 * 10)
    return 1 + (s >= 3) + (s >= 5) + (s >= 7) + (s >= 9)


CRITERIA = {
    "plan_quality": ("Plan Quality",
                     "Judge whether the Planner's three steps form a useful plan for answering the question: relevant to the question, specific, "
                     "complete enough to answer it, and in a sensible order.",
                     [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]),
    "writer_helpfulness": ("Writer Helpfulness",
                           "Judge whether the Writer's draft answers the question accurately and usefully. Penalise answers that are wrong, "
                           "evasive, off-topic or that invent facts the question did not supply.",
                           [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]),
    "final_helpfulness": ("Final Answer Helpfulness",
                          "Judge whether the final answer is helpful and relevant to the question: it must answer what was asked, be clear, "
                          "and not invent facts.",
                          [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]),
}


def make_metric(key: str, judge: DeepEvalBaseLLM) -> GEval:
    name, criteria, params = CRITERIA[key]
    rubric = [Rubric(score_range=rng, expected_outcome=text) for rng, text in BANDS]
    return GEval(name=name, criteria=criteria, evaluation_params=params, rubric=rubric, model=judge, async_mode=False, threshold=0.5)


def score(key: str, judge: DeepEvalBaseLLM, question: str, text: str) -> dict:
    """One criterion, one text -> {score 1-5, raw 0-1, reason, judge_ms}. Raises JudgeUnavailable when the judge cannot answer."""
    metric = make_metric(key, judge)
    t0 = time.perf_counter()
    metric.measure(LLMTestCase(input=question, actual_output=text))
    return {"score": band_to_score(metric.score), "raw": metric.score, "reason": metric.reason, "judge_ms": round((time.perf_counter() - t0) * 1000, 1)}
