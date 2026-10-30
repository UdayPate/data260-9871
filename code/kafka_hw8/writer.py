"""HW8 Part 2 - Writer: reads a plan from <PREFIX>_tasks, sends a draft answer to <PREFIX>_drafts.
All Writer instances share one consumer group, so Kafka splits the tasks topic's partitions between them.

WRITER_MODE=stub (Part 3 failure tests only) swaps the model call for a deterministic draft that sleeps for the
message's own `work_s` seconds. Everything else - validation, Kafka, retries, commits - is the same code path."""

import logging
import os
import time

from agent_common import DRAFTS, PREFIX, TASKS, ask_model, run_stage, stage_name

SYSTEM = (
    "You are the Writer for a community sports league office. Answer the question by following the plan "
    "step by step. Write plain prose, at most 120 words, no markdown headings."
)
STUB = os.environ.get("WRITER_MODE", "model") == "stub"
log = logging.getLogger(stage_name("writer"))  # handler is attached by run_stage


def write(message: dict) -> dict:
    plan = message.get("plan")
    if not isinstance(plan, list) or not plan or not all(isinstance(s, str) and s.strip() for s in plan):
        raise ValueError("plan must be a non-empty list of non-empty strings")
    corr = message["correlation_id"]
    log.info("WORK start corr=%s", corr)
    if STUB:
        time.sleep(float(message.get("work_s", 0)))
        draft = "[stub draft] " + " ".join(plan)
    else:
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1))
        draft = ask_model(SYSTEM, f"Question: {message['question']}\n\nPlan:\n{steps}", temperature=0.5)
    log.info("WORK done corr=%s", corr)
    out = {"question": message["question"], "plan": plan, "draft": draft}
    out.update({k: message[k] for k in ("entity_id", "entity_seq") if k in message})
    return out


if __name__ == "__main__":
    run_stage("writer", TASKS, DRAFTS, f"{PREFIX}_writers", write)
