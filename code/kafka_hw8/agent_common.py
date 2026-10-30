"""
DATA-260 Homework 8 Part 2 - what the Planner, Writer and Reviewer share.

Topics:  s9871_inbox -> [planner] -> s9871_tasks -> [writer] -> s9871_drafts -> [reviewer] -> s9871_final
No agent calls another: every hand-off is a Kafka message, and correlation_id is copied unchanged
from the question to the final answer.

run_stage() is the one consume -> handle -> produce -> commit loop. The offset is committed only after
the output message has been delivered, so a crash in between means redelivery, never loss.

HW8 Part 3 adds three switchable behaviours. HW8_MODE=fixed (the default) turns all three on, HW8_MODE=naive
turns them off so each "before fix" result is a real run of the same code:

    behaviour        fixed                                   naive
    idempotency      skip a correlation_id already handled   handle every delivery
    offset commit    after the output message is delivered   before processing (at-most-once)
    poison message   3 attempts, then <PREFIX>_dead_letter   retry forever, never commit

Each can also be overridden alone with HW8_IDEMPOTENT=1|0, HW8_COMMIT=after|before,
HW8_POISON=dlq|retry-forever (the poison "before" run uses HW8_COMMIT=after so only the retry policy differs).
"""

import json
import os
import re
import signal
import sqlite3
import sys
import time
from pathlib import Path

from confluent_kafka import Consumer, KafkaError, Producer

from common import BOOTSTRAP, PREFIX, setup_logging

INBOX, TASKS, DRAFTS, FINAL = (f"{PREFIX}_{t}" for t in ("inbox", "tasks", "drafts", "final"))

DEAD_LETTER = f"{PREFIX}_dead_letter"
MODE = os.environ.get("HW8_MODE", "fixed")
IDEMPOTENT = os.environ.get("HW8_IDEMPOTENT", "1" if MODE == "fixed" else "0") == "1"
COMMIT = os.environ.get("HW8_COMMIT", "after" if MODE == "fixed" else "before")
POISON = os.environ.get("HW8_POISON", "dlq" if MODE == "fixed" else "retry-forever")
MAX_ATTEMPTS = int(os.environ.get("HW8_MAX_ATTEMPTS", "3"))
RETRY_PAUSE_S = float(os.environ.get("HW8_RETRY_PAUSE_S", "0.5"))
GROUP_SUFFIX = os.environ.get("HW8_GROUP_SUFFIX", "")  # lets a test use a fresh consumer group
INSTANCE = os.environ.get("HW8_INSTANCE", "")  # "A", "B": tells two Writers apart in the logs
STATE_DIR = Path(os.environ.get("HW8_STATE_DIR", Path(__file__).resolve().parent / "state"))

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # ModelClient lives in src/ (HW1)


def stage_name(stage: str) -> str:
    return f"{stage}-{INSTANCE}" if INSTANCE else stage


class ProcessedStore:
    """Durable set of correlation_ids a stage has finished (SQLite file, shared by that stage's instances)."""

    def __init__(self, stage: str):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(STATE_DIR / f"processed_{stage}.db", timeout=30, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS processed (correlation_id TEXT PRIMARY KEY)")

    def seen(self, corr: str) -> bool:
        return self.db.execute("SELECT 1 FROM processed WHERE correlation_id=?", (corr,)).fetchone() is not None

    def mark(self, corr: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO processed VALUES (?)", (corr,))


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


def tags(message: dict) -> str:
    """entity/seq of the ordering test's messages, so the processing order can be read from the log."""
    return f" entity={message['entity_id']} seq={message['entity_seq']}" if "entity_id" in message else ""


def run_stage(stage: str, in_topic: str, out_topic: str, group: str, handler) -> None:
    """handler(message: dict) -> dict. correlation_id is carried over from the input, never regenerated."""
    name, group = stage_name(stage), group + GROUP_SUFFIX
    log = setup_logging(name)
    store = ProcessedStore(stage) if IDEMPOTENT else None
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "auto.offset.reset": "earliest",
                         "enable.auto.commit": False, "session.timeout.ms": 10000})
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    running = [True]
    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))

    def send(topic: str, key: str, payload: dict):
        """Produce and wait for the broker's ack. Returns the delivered message, or None on failure."""
        delivered = []
        producer.produce(topic, key=key, value=json.dumps(payload), on_delivery=lambda e, m: delivered.append((e, m)))
        producer.flush(10)
        err, sent = delivered[0] if delivered else ("not delivered", None)
        if err:
            log.error("SEND FAILED topic=%s corr=%s: %s (offset not committed, will be redelivered)", topic, key, err)
            return None
        return sent

    def on_assign(c, parts):
        log.info("Assigned partitions: %s", [p.partition for p in parts])
        log.info("Consumer is ready and listening... topic=%s group=%s mode=%s idempotent=%s commit=%s poison=%s",
                 in_topic, group, MODE, IDEMPOTENT, COMMIT, POISON)

    def commit(msg, when: str) -> None:
        consumer.commit(msg, asynchronous=False)
        log.info("COMMITTED %s offset=%d (next to read = %d)", when, msg.offset(), msg.offset() + 1)

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
            commit(msg, "skipped message")
            continue
        where = f"partition={msg.partition()} offset={msg.offset()}"
        log.info("RECEIVED topic=%s %s corr=%s%s", msg.topic(), where, corr, tags(message))
        if COMMIT == "before":
            commit(msg, "BEFORE processing")
        if store and store.seen(corr):
            log.info("DUPLICATE corr=%s already processed, skipped (no output, no side effect)", corr)
            if COMMIT == "after":
                commit(msg, "duplicate")
            continue

        attempt, out, error = 0, None, None
        while running[0]:
            attempt += 1
            try:
                out = handler(message)
                break
            except Exception as exc:  # any handler failure counts as a failed attempt
                error = f"{type(exc).__name__}: {exc}"
                limit = f"{attempt}/{MAX_ATTEMPTS}" if POISON == "dlq" else f"{attempt}/unbounded"
                log.warning("ATTEMPT %s failed corr=%s: %s", limit, corr, error)
                if POISON == "dlq" and attempt >= MAX_ATTEMPTS:
                    break
                time.sleep(RETRY_PAUSE_S)
        if out is None and not (POISON == "dlq" and attempt >= MAX_ATTEMPTS and error):
            break  # shutting down in the middle of retries: leave the offset uncommitted
        if out is None:
            letter = {"correlation_id": corr, "stage": stage, "error": error, "attempts": attempt,
                      "source_topic": msg.topic(), "source_partition": msg.partition(),
                      "source_offset": msg.offset(), "original": msg.value().decode("utf-8", "replace")}
            sent = send(DEAD_LETTER, corr, letter)
            if sent is None:
                continue
            log.info("DEAD-LETTERED corr=%s after %d attempts -> topic=%s partition=%d offset=%d error=%s", corr,
                     attempt, sent.topic(), sent.partition(), sent.offset(), error)
            if COMMIT == "after":
                commit(msg, "after dead-lettering")
            continue

        out["correlation_id"] = corr
        log.info("PROCESSED corr=%s %s%s", corr, where, tags(message))
        sent = send(out_topic, corr, out)
        if sent is None:
            continue
        log.info("SENT topic=%s partition=%d offset=%d corr=%s body=%s", sent.topic(), sent.partition(),
                 sent.offset(), corr, json.dumps(out))
        if store:
            store.mark(corr)
        if COMMIT == "after":
            commit(msg, "AFTER successful processing")
    consumer.close()
    log.info("Consumer closed, left the group")
