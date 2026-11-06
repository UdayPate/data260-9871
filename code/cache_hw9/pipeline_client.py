"""
DATA-260 Homework 9 - Part 2: the cache-miss path = the unchanged HW8 agent pipeline.

PipelineClient.ask(text) does what HW8's send_question.py does (inbox -> Planner -> Writer -> Reviewer -> final, correlation_id preserved) but
keeps its Kafka producer/consumer open between questions. Reuses HW8's topic names and settings from code/kafka_hw8/agent_common.py.
"""

import json
import sys
import time
import uuid
from pathlib import Path

from confluent_kafka import OFFSET_END, Consumer, Producer, TopicPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kafka_hw8"))
from agent_common import BOOTSTRAP, FINAL, INBOX  # noqa: E402


class PipelineClient:
    def __init__(self, timeout_s: float = 300.0):
        self.timeout_s = timeout_s
        self.producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
        self.consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"hw9-ingress-{uuid.uuid4().hex[:8]}", "enable.auto.commit": False})
        parts = self.consumer.list_topics(FINAL, timeout=15).topics[FINAL].partitions
        self.consumer.assign([TopicPartition(FINAL, p, OFFSET_END) for p in parts])
        self.consumer.poll(1.0)  # resolve the end offsets before the first question is sent

    def ask(self, question: str) -> dict:
        """Returns the pipeline's final message {status, answer, review, correlation_id}, or {status: 'timeout'} if none arrives in time."""
        corr = str(uuid.uuid4())
        self.producer.produce(INBOX, key=corr, value=json.dumps({"correlation_id": corr, "question": question}))
        self.producer.flush(10)
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            msg = self.consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            final = json.loads(msg.value())
            if final.get("correlation_id") == corr:
                return final
        return {"correlation_id": corr, "status": "timeout", "answer": ""}

    def close(self) -> None:
        self.consumer.close()
