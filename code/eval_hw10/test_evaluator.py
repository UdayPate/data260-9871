"""HW10 Part 2 checks for the evaluator's bounds. Real objects, no mocks: an unreachable Ollama endpoint, a trace id that never existed, a missing piece.
    code\\venv\\Scripts\\python.exe code/eval_hw10/test_evaluator.py      (needs Kafka up; does not need the model)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluator  # noqa: E402
import judge as jd  # noqa: E402

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


rec = lambda v: {"value": v, "topic": "t", "partition": 0, "offset": 0, "timestamp_ms": 0}  # noqa: E731
bundle = {"plan": rec({"question": "q", "plan": ["a", "b", "c"]}), "draft": rec({"question": "q", "draft": "text"}),
          "final": rec({"status": "approved", "answer": "text"})}

dead = jd.LocalJudge(timeout_s=3, host="http://127.0.0.1:9")  # nothing listens on port 9
t = time.time()
r = evaluator.evaluate("t-dead", bundle, dead)
check("unavailable judge -> judge_unavailable, no scores, returns promptly", r["status"] == "judge_unavailable" and "scores" not in r and time.time() - t < 15,
      f"status={r['status']} in {time.time() - t:.1f}s error={r['error'][:60]}")

r = evaluator.evaluate("t-missing", {"plan": bundle["plan"]}, dead)
check("missing draft/final -> incomplete, judge never called", r["status"] == "incomplete" and "draft" in r["error"] and "final" in r["error"], r["error"])

t = time.time()
found, stats = evaluator.collect({"no-such-trace-id"}, timeout_s=4)
check("collect for an unknown trace_id gives up at its deadline", stats["timed_out"] and found == {"no-such-trace-id": {}} and time.time() - t < 20,
      f"{time.time() - t:.1f}s stats={stats}")

check("identical text, equal scores -> 'no improvement, as expected'", "no improvement" in evaluator.interpret(3, 3, True, "approved"))
check("identical text, different scores -> judge variation, not improvement", "not an improvement" in evaluator.interpret(3, 4, True, "approved"))
check("different text, higher score -> improved", "improved" in evaluator.interpret(2, 4, False, "approved"))
check("different text, lower score -> worse", "worse" in evaluator.interpret(4, 2, False, "approved"))
check("score bands: 0-2->1, 3-4->2, 5-6->3, 7-8->4, 9-10->5", [jd.band_to_score(x / 10) for x in range(11)] == [1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
print(f"\n{'ALL PASSED' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
