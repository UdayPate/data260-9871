"""
DATA-260 Homework 8 Part 2 - what the Planner, Writer and Reviewer share.

Topics:  s9871_inbox -> [planner] -> s9871_tasks -> [writer] -> s9871_drafts -> [reviewer] -> s9871_final
No agent calls another: every hand-off is a Kafka message, and correlation_id is copied unchanged
from the question to the final answer.

run_stage() is the one consume -> handle -> produce -> commit loop. The offset is committed only after
the output message has been delivered, so a crash in between means redelivery, never loss.
"""

import json
import re
import signal
import sys
from pathlib import Path

from confluent_kafka import Consumer, KafkaError, Producer

from common import BOOTSTRAP, PREFIX, setup_logging

INBOX, TASKS, DRAFTS, FINAL = (f"{PREFIX}_{t}" for t in ("inbox", "tasks", "drafts", "final"))

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # ModelClient lives in src/ (HW1)


def ask_model(system: str, user: str, temperature: float = 0.3) -> str:
    """One stateless call to the local qwen3:8b (fresh client, so no history builds up; thinking off)."""
    from model_client import ModelClient
    client = ModelClient(model="qwen3:8b", temperature=temperature, reasoning=False, seed=9871)
    return client.complete([{"role": "system", "content": system}, {"role": "user", "content": user}]).strip()


def parse_json_object(text: str) -> dict:
    """First {...} block in the model's reply, as a dict (models sometimes wrap JSON in prose or fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model reply: {text[:120]!r}")
    return json.loads(match.group(0))


def run_stage(name: str, in_topic: str, out_topic: str, group: str, handler) -> None:
    """handler(message: dict) -> dict. correlation_id is carried over from the input, never regenerated."""
    log = setup_logging(name)
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "auto.offset.reset": "earliest",
                         "enable.auto.commit": False, "session.timeout.ms": 10000})
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    running = [True]
    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))

    def on_assign(c, parts):
        log.info("Assigned partitions: %s", [p.partition for p in parts])
        log.info("Consumer is ready and listening... topic=%s group=%s", in_topic, group)

    consumer.subscribe([in_topic], on_assign=on_assign)
    while running[0]:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                log.error("consumer error: %s", msg.error())
            continue
        try:
            message = json.loads(msg.value())
            corr = message["correlation_id"]
        except (ValueError, KeyError, TypeError):
            log.warning("SKIP partition=%d offset=%d: not JSON with a correlation_id", msg.partition(), msg.offset())
            consumer.commit(msg, asynchronous=False)
            continue
        log.info("RECEIVED topic=%s partition=%d offset=%d corr=%s", msg.topic(), msg.partition(), msg.offset(), corr)
        out = handler(message)
        out["correlation_id"] = corr
        log.info("PROCESSED corr=%s", corr)
        delivered = []
        producer.produce(out_topic, key=corr, value=json.dumps(out), on_delivery=lambda e, m: delivered.append((e, m)))
        producer.flush(10)
        err, sent = delivered[0] if delivered else ("not delivered", None)
        if err:
            log.error("SEND FAILED corr=%s: %s (offset not committed, will be redelivered)", corr, err)
            continue
        log.info("SENT topic=%s partition=%d offset=%d corr=%s body=%s", sent.topic(), sent.partition(),
                 sent.offset(), corr, json.dumps(out))
        consumer.commit(msg, asynchronous=False)
        log.info("COMMITTED input offset=%d", msg.offset() + 1)
    consumer.close()
    log.info("Consumer closed, left the group")
