"""
DATA-260 Homework 10 Part 2 - the evaluator for the Planner/Writer/Reviewer Kafka pipeline.

collect(trace_ids)   reads the plan (<PREFIX>_tasks), the draft (<PREFIX>_drafts) and the final answer (<PREFIX>_final) from Kafka and joins them on
                     correlation_id (= trace_id). The original message value plus topic/partition/offset/timestamp are kept so the evaluation can be redone.
                     Bounded: it stops at its deadline, skips malformed messages (counted) and reports which pieces are missing.
evaluate(bundle)     scores one request with the local judge: Plan Quality, Writer Helpfulness, Final Answer Helpfulness and Final-vs-Draft
                     Improvement. A judge that is down or too slow gives status "judge_unavailable" for that request after at most JUDGE_TIMEOUT_S per call.
                     Each evaluation writes an "evaluation" span for the same trace_id.
"""

import json
import sys
import time
import uuid
from pathlib import Path

from confluent_kafka import Consumer, TopicPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kafka_hw8"))
import judge as jd  # noqa: E402
import tracing  # noqa: E402
from agent_common import BOOTSTRAP, DRAFTS, FINAL, TASKS  # noqa: E402

KINDS = {TASKS: "plan", DRAFTS: "draft", FINAL: "final"}


def collect(trace_ids: set[str], timeout_s: float = 60.0) -> tuple[dict, dict]:
    """-> ({trace_id: {"plan": rec, "draft": rec, "final": rec}}, stats). rec = {"value": parsed message, "topic", "partition", "offset", "timestamp_ms"}."""
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"hw10-eval-{uuid.uuid4().hex[:8]}", "enable.auto.commit": False,
                         "auto.offset.reset": "earliest"})
    found: dict[str, dict] = {t: {} for t in trace_ids}
    stats = {"messages_read": 0, "malformed_skipped": 0, "timed_out": False}
    try:
        meta = consumer.list_topics(timeout=15).topics
        consumer.assign([TopicPartition(t, p, 0) for t in KINDS for p in meta[t].partitions])
        deadline = time.time() + timeout_s
        while time.time() < deadline and not all(len(v) == 3 for v in found.values()):
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            stats["messages_read"] += 1
            try:
                value = json.loads(msg.value())
                corr = value["correlation_id"]
            except (ValueError, KeyError, TypeError):
                stats["malformed_skipped"] += 1
                continue
            if corr in found:
                found[corr][KINDS[msg.topic()]] = {"value": value, "topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(),
                                                   "timestamp_ms": msg.timestamp()[1]}
        stats["timed_out"] = not all(len(v) == 3 for v in found.values())
    finally:
        consumer.close()
    return found, stats


def interpret(draft_score: int, final_score: int, identical: bool, status: str) -> str:
    diff = final_score - draft_score
    if identical:
        base = ("The Reviewer returned the Writer's draft word for word (it only approves or rejects), so the final answer cannot be better than the draft. "
                "Reviewer status: " + status + ".")
        if diff == 0:
            return base + " Both scores are equal: no improvement, as expected."
        return base + f" The scores differ by {diff:+d} only because the two criteria are worded differently; this is judge variation, not an improvement."
    if diff > 0:
        return f"The final answer scored {diff} point(s) higher than the draft: the Reviewer stage improved the answer."
    if diff < 0:
        return f"The final answer scored {-diff} point(s) lower than the draft: the Reviewer stage made the answer worse."
    return "The final answer text differs from the draft but scored the same: no measurable improvement."


def evaluate(trace_id: str, bundle: dict, judge: jd.DeepEvalBaseLLM, model_name: str = jd.JUDGE_MODEL) -> dict:
    """bundle = {"plan": rec, "draft": rec, "final": rec} from collect(); a missing piece makes the case "incomplete" (nothing is scored)."""
    t0 = tracing.now_ms()
    record = {"trace_id": trace_id, "status": "ok", "error": None, "judge": {"model": model_name, "temperature": jd.JUDGE_TEMPERATURE,
              "seed": jd.JUDGE_SEED, "scale": jd.SCALE}, "inputs": bundle}
    missing = [k for k in ("plan", "draft", "final") if k not in bundle]
    if missing:
        record.update(status="incomplete", error=f"missing {', '.join(missing)} message(s) for this correlation_id")
        tracing.emit(trace_id, "evaluation", t0, tracing.now_ms(), "error", record["error"])
        return record
    plan, draft, final = bundle["plan"]["value"], bundle["draft"]["value"], bundle["final"]["value"]
    question = draft.get("question") or plan.get("question", "")
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(plan.get("plan", []), 1))
    try:
        p = jd.score("plan_quality", judge, question, steps)
        w = jd.score("writer_helpfulness", judge, question, draft.get("draft", ""))
        f = jd.score("final_helpfulness", judge, question, final.get("answer", ""))
    except jd.JudgeUnavailable as exc:
        record.update(status="judge_unavailable", error=str(exc))
        tracing.emit(trace_id, "evaluation", t0, tracing.now_ms(), "error", str(exc))
        return record
    identical = draft.get("draft", "").strip() == final.get("answer", "").strip()
    record["scores"] = {
        "plan_quality": {"score": p["score"], "reason": p["reason"], "raw": p["raw"]},
        "writer_helpfulness": {"score": w["score"], "trace_id": trace_id, "reason": w["reason"], "raw": w["raw"]},
        "final_helpfulness": {"score": f["score"], "final_answer": final.get("answer", ""), "reason": f["reason"], "raw": f["raw"]},
        "final_vs_draft": {"draft_score": w["score"], "final_score": f["score"], "difference": f["score"] - w["score"], "final_equals_draft": identical,
                           "reviewer_status": final.get("status"), "interpretation": interpret(w["score"], f["score"], identical, final.get("status", ""))}}
    record["judge_ms"] = round(p["judge_ms"] + w["judge_ms"] + f["judge_ms"], 1)
    tracing.emit(trace_id, "evaluation", t0, tracing.now_ms(), judge_ms=record["judge_ms"], criteria=4)
    return record
