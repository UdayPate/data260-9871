"""
DATA-260 Homework 8 Part 1 - the complete request/response flow, CREATE_ENTITY then GET_ENTITY.

Run from the repo root while `docker compose up` is running:
    code\\venv\\Scripts\\python.exe code/kafka_hw8/homework_demo.py

This process is the Kafka client (kafka_rpc.KafkaRpcClient). The worker runs in its own container, so
the "worker received / processed / replied" lines are the worker's real log lines, read back from
`docker logs s9871-worker` for the same correlation_id (nothing is simulated).
"""

import json
import logging
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta

from common import REQUEST_TOPIC, RESPONSE_TOPIC, setup_logging
from kafka_rpc import KafkaRpcClient

log = setup_logging("client")


class Buffer(logging.Handler):
    """Holds the client's log lines so they can be printed in causal order next to the worker's lines."""

    def __init__(self, inner: logging.Handler):
        super().__init__()
        self.inner, self.lines = inner, []

    def emit(self, record):
        self.lines.append(self.inner.format(record))


buffer = Buffer(log.handlers[0])
log.handlers[:] = [buffer]
DOCKER = shutil.which("docker") or shutil.which("docker.exe") or "docker"
FIXTURE = {
    "fixture_name": "Milpitas Lions vs San Jose Tigers",
    "teams_players": "Milpitas Lions (A. Singh, R. Gomez); San Jose Tigers (L. Chen, M. Okafor)",
    "submitter_email": "league-office@leaguemail.com",
    "description": "Rivalry match, gates open 9am, toss at 9:30am.",
    "category": "Soccer",
    "agree_terms": True,
}


def worker_lines(corr: str, since: datetime) -> list[str]:
    """The worker's own log lines for this correlation_id, newest run only."""
    out = subprocess.run([DOCKER, "logs", "--since", since.strftime("%Y-%m-%dT%H:%M:%S"), "s9871-worker"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [ln for ln in out.splitlines() if corr in ln]


def banner(text: str) -> None:
    print(f"\n=== {text} ===")


def run_operation(client: KafkaRpcClient, label: str, operation: str, data: dict, corr: str) -> dict:
    since = datetime.now() - timedelta(seconds=2)
    banner(f"{label}: {operation} (correlation_id={corr})")
    log.info("Sending %s to %s", operation, REQUEST_TOPIC)
    response = client.request(operation, data, correlation_id=corr)
    log.info("Response returned to caller: %s", json.dumps(response))
    time.sleep(0.5)  # let the worker's last log line reach `docker logs`
    mine, buffer.lines = buffer.lines, []
    after = [ln for ln in mine if "RECEIVED response" in ln or "Response returned" in ln]
    for line in [ln for ln in mine if ln not in after]:
        print(line)
    for line in worker_lines(corr, since):
        print("  [from docker logs s9871-worker]", line)
    for line in after:
        print(line)
    return response


def main() -> int:
    print("Lines are printed in causal order (send -> worker -> client receive). The worker's clock runs in the")
    print("Docker VM and can differ from this host's clock by a few hundred ms, so compare offsets, not timestamps.")
    client = KafkaRpcClient(log)
    try:
        banner("Step 1: create one correlation_id")
        create_corr = str(uuid.uuid4())
        print("correlation_id =", create_corr)
        created = run_operation(client, "Steps 2-6", "CREATE_ENTITY", FIXTURE, create_corr)
        banner("Step 7: extract the generated entity_id")
        entity_id = created.get("entity_id")
        print("entity_id =", entity_id)
        if not created.get("success") or not entity_id:
            print("CREATE_ENTITY failed; stopping.")
            return 1
        get_corr = str(uuid.uuid4())
        fetched = run_operation(client, "Steps 8-9", "GET_ENTITY", {"entity_id": entity_id}, get_corr)
        banner("Step 10: retrieved entity and correlation_id check")
        print(json.dumps(fetched, indent=2))
        checks = {
            "CREATE response echoes the CREATE correlation_id": created.get("correlation_id") == create_corr,
            "GET response echoes the GET correlation_id": fetched.get("correlation_id") == get_corr,
            "GET returned success=true": fetched.get("success") is True,
            "retrieved entity_id equals the created entity_id": fetched.get("entity", {}).get("entity_id") == entity_id,
            "retrieved fields equal the submitted fields": {k: v for k, v in fetched.get("entity", {}).items()
                                                            if k != "entity_id"} == FIXTURE,
        }
        for name, ok in checks.items():
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print(f"topics: requests={REQUEST_TOPIC} responses={RESPONSE_TOPIC}")
        return 0 if all(checks.values()) else 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
