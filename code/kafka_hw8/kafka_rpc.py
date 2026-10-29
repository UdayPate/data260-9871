"""
DATA-260 Homework 8 Part 1 - request/response client over Kafka.

KafkaRpcClient.request() creates the correlation_id once (or accepts one from the caller), produces the
request to <PREFIX>_entity_requests and blocks until the response carrying the same correlation_id arrives
on <PREFIX>_entity_responses. Used by both the FastAPI wrapper (api.py) and homework_demo.py.

The response consumer uses assign() at the end offset instead of a consumer group, so it never needs a
rebalance and only sees responses to requests sent after it started.
"""

import json
import threading
import uuid

from confluent_kafka import Consumer, Producer, TopicPartition, OFFSET_END

from common import BOOTSTRAP, REQUEST_TOPIC, RESPONSE_TOPIC


class KafkaRpcClient:
    def __init__(self, log, bootstrap: str = BOOTSTRAP):
        self.log = log
        self.producer = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
        self.consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": f"client-{uuid.uuid4().hex[:8]}",
                                  "enable.auto.commit": False})
        meta = self.consumer.list_topics(RESPONSE_TOPIC, timeout=15)
        parts = meta.topics[RESPONSE_TOPIC].partitions
        self.consumer.assign([TopicPartition(RESPONSE_TOPIC, p, OFFSET_END) for p in parts])
        self._pending: dict[str, tuple[threading.Event, list]] = {}
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self) -> None:
        while not self._stop:
            msg = self.consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            try:
                response = json.loads(msg.value())
            except ValueError:
                continue
            corr = response.get("correlation_id")
            with self._lock:
                waiter = self._pending.get(corr)
            if waiter is None:
                continue  # someone else's response (another client) - ignore
            self.log.info("RECEIVED response topic=%s partition=%d offset=%d corr=%s success=%s body=%s", msg.topic(),
                          msg.partition(), msg.offset(), corr, response.get("success"), msg.value().decode())
            waiter[1].append(response)
            waiter[0].set()

    def request(self, operation: str, data: dict, correlation_id: str | None = None, timeout: float = 10.0) -> dict:
        corr = correlation_id or str(uuid.uuid4())  # created once, never changed afterwards
        message = {"correlation_id": corr, "reply_to": RESPONSE_TOPIC, "operation": operation, "data": data}
        waiter = (threading.Event(), [])
        with self._lock:
            self._pending[corr] = waiter

        def delivered(err, msg):
            if err:
                self.log.error("SEND FAILED corr=%s: %s", corr, err)
            else:
                self.log.info("SENT request topic=%s partition=%d offset=%d corr=%s op=%s body=%s", msg.topic(),
                              msg.partition(), msg.offset(), corr, operation, msg.value().decode())

        self.producer.produce(REQUEST_TOPIC, key=corr, value=json.dumps(message), on_delivery=delivered)
        self.producer.flush(10)
        try:
            if not waiter[0].wait(timeout):
                return {"correlation_id": corr, "success": False, "error": "Timed out waiting for worker response"}
            return waiter[1][0]
        finally:
            with self._lock:
                self._pending.pop(corr, None)

    def close(self) -> None:
        self._stop = True
        self._thread.join(2)
        self.consumer.close()
