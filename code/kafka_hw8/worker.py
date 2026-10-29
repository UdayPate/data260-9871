"""
DATA-260 Homework 8 Part 1 - the Fixture worker.

Consumes <PREFIX>_entity_requests, validates and processes CREATE_ENTITY / GET_ENTITY against a plain
Python dict, and replies on the topic named by the request's reply_to, echoing correlation_id unchanged.
The offset is committed only after the reply has been delivered (at-least-once).
"""

import json
import signal
import uuid

from confluent_kafka import Consumer, KafkaError, Producer

from common import BOOTSTRAP, PREFIX, REQUEST_TOPIC, RESPONSE_TOPIC, setup_logging, validate_fixture

log = setup_logging("worker")

store: dict[str, dict] = {}  # entity_id -> fixture (plain dict, per the assignment)


def handle_request(request: dict) -> dict:
    """Pure request -> response logic (no Kafka). The caller adds nothing: correlation_id is set here."""
    response: dict = {"correlation_id": request.get("correlation_id")}
    operation, data = request.get("operation"), request.get("data")
    if operation == "CREATE_ENTITY":
        fixture, error = validate_fixture(data)
        if error:
            return {**response, "success": False, "error": error}
        entity_id = str(uuid.uuid4())
        store[entity_id] = {"entity_id": entity_id, **fixture}
        return {**response, "success": True, "entity_id": entity_id, "message": "Entity created"}
    if operation == "GET_ENTITY":
        entity_id = data.get("entity_id") if isinstance(data, dict) else None
        if not isinstance(entity_id, str) or not entity_id:
            return {**response, "success": False, "error": "entity_id is required"}
        if entity_id not in store:
            return {**response, "success": False, "error": "Entity not found"}
        return {**response, "success": True, "entity": store[entity_id]}
    return {**response, "success": False, "error": "Unknown operation"}


def parse_request(raw: bytes) -> tuple[dict | None, str | None]:
    """Return (request, None), or (None, reason) when it cannot even be answered."""
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, "not valid JSON"
    if not isinstance(request, dict) or not isinstance(request.get("correlation_id"), str) or not request["correlation_id"]:
        return None, "missing correlation_id"
    return request, None


def reply_topic(request: dict) -> str:
    """Honour reply_to only for this project's own topics; otherwise fall back to the response topic."""
    target = request.get("reply_to")
    return target if isinstance(target, str) and target.startswith(f"{PREFIX}_") else RESPONSE_TOPIC


def main() -> None:
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": f"{PREFIX}_entity_workers",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "session.timeout.ms": 10000,  # a killed worker is declared dead (and its partition reassigned) after 10 s
    })
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    def on_assign(c, parts):
        log.info("Assigned partitions: %s", [p.partition for p in parts])
        log.info("Consumer is ready and listening... topic=%s group=%s", REQUEST_TOPIC, f"{PREFIX}_entity_workers")

    consumer.subscribe([REQUEST_TOPIC], on_assign=on_assign)
    running = [True]
    # docker stop sends SIGTERM: leave the group cleanly so the partition is handed over at once.
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
    while running[0]:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                log.error("consumer error: %s", msg.error())
            continue
        request, problem = parse_request(msg.value())
        if request is None:
            log.warning("SKIP partition=%d offset=%d: %s", msg.partition(), msg.offset(), problem)
            consumer.commit(msg, asynchronous=False)
            continue
        corr = request["correlation_id"]
        log.info("RECEIVED topic=%s partition=%d offset=%d corr=%s op=%s", msg.topic(), msg.partition(),
                 msg.offset(), corr, request.get("operation"))
        response = handle_request(request)
        log.info("PROCESSED corr=%s op=%s success=%s %s", corr, request.get("operation"), response["success"],
                 response.get("error") or response.get("message") or "entity returned")
        target = reply_topic(request)
        delivered = []
        producer.produce(target, key=corr, value=json.dumps(response),
                         on_delivery=lambda err, m: delivered.append((err, m)))
        producer.flush(10)
        err, sent = delivered[0] if delivered else ("not delivered", None)
        if err:
            log.error("REPLY FAILED corr=%s: %s (offset not committed, will be redelivered)", corr, err)
            continue
        log.info("REPLIED topic=%s partition=%d offset=%d corr=%s success=%s", sent.topic(), sent.partition(),
                 sent.offset(), corr, response["success"])
        consumer.commit(msg, asynchronous=False)
    consumer.close()
    log.info("Consumer closed, left the group")


if __name__ == "__main__":
    main()
