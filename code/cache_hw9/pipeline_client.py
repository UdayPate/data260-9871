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
import tracing  # noqa: E402
from agent_common import BOOTSTRAP, FINAL, INBOX  # noqa: E402


class PipelineClient:
    def __init__(self, timeout_s: float = 300.0):
        self.timeout_s = timeout_s
        self.producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
        self.consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"hw9-ingress-{uuid.uuid4().hex[:8]}", "enable.auto.commit": False})
        parts = self.consumer.list_topics(FINAL, timeout=15).topics[FINAL].partitions
        self.consumer.assign([TopicPartition(FINAL, p, OFFSET_END) for p in parts])
        self.consumer.poll(1.0)  # resolve the end offsets before the first question is sent

    def ask(self, question: str, trace_id: str | None = None) -> dict:
        """Returns the pipeline's final message {status, answer, review, correlation_id}, or {status: 'timeout'} if none arrives in time.
        HW10: trace_id (when given) is used as the correlation_id, so the request keeps one identifier from the cache lookup to the evaluator."""
        corr = trace_id or str(uuid.uuid4())
        t0 = tracing.now_ms()
        self.producer.produce(INBOX, key=corr, value=json.dumps({"correlation_id": corr, "question": question}))
        self.producer.flush(10)
        t1 = tracing.now_ms()
        tracing.emit(corr, "inbox", t0, t1, topic=INBOX)
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            msg = self.consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            final = json.loads(msg.value())
            if final.get("correlation_id") == corr:
                t2 = tracing.now_ms()
                tracing.emit(corr, "final", tracing.kafka_ms(msg) or t1, t2, topic=FINAL, pipeline_status=final.get("status"))
                return final
        tracing.emit(corr, "final", t1, tracing.now_ms(), "error", f"no message on {FINAL} within {self.timeout_s:.0f} s", topic=FINAL)
        return {"correlation_id": corr, "status": "timeout", "answer": ""}

    def close(self) -> None:
        self.consumer.close()
