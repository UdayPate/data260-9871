"""
HW8 Part 2 - "You": send a question to <PREFIX>_inbox and wait for the answer on <PREFIX>_final.
Usage: python send_question.py ["question text"]
"""

import json
import sys
import time
import uuid

from confluent_kafka import Consumer, OFFSET_END, Producer, TopicPartition

from agent_common import BOOTSTRAP, FINAL, INBOX, setup_logging

DEFAULT_QUESTION = "What should a league office check before scheduling a Soccer fixture on a shared field?"


def main() -> int:
    log = setup_logging("you")
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    corr = str(uuid.uuid4())
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"you-{corr[:8]}", "enable.auto.commit": False})
    parts = consumer.list_topics(FINAL, timeout=15).topics[FINAL].partitions
    consumer.assign([TopicPartition(FINAL, p, OFFSET_END) for p in parts])
    consumer.poll(1.0)  # make sure the end offsets are resolved before sending
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    body = json.dumps({"correlation_id": corr, "question": question})
    done = []
    producer.produce(INBOX, key=corr, value=body, on_delivery=lambda e, m: done.append((e, m)))
    producer.flush(10)
    err, sent = done[0]
    if err:
        log.error("SEND FAILED: %s", err)
        return 1
    log.info("SENT topic=%s partition=%d offset=%d corr=%s body=%s", sent.topic(), sent.partition(), sent.offset(),
             corr, body)
    deadline = time.time() + 600
    while time.time() < deadline:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        final = json.loads(msg.value())
        if final.get("correlation_id") == corr:
            log.info("RECEIVED topic=%s partition=%d offset=%d corr=%s", msg.topic(), msg.partition(), msg.offset(), corr)
            print(json.dumps(final, indent=2))
            consumer.close()
            return 0
    log.error("no answer for corr=%s within 600 s", corr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
