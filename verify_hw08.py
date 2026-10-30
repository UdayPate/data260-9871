"""
DATA-260 Homework 8 - verify_hw08.py
A smoke test that starts the real Kafka system and checks that the basics work. Writes reports/hw08/verification.json.
It does NOT modify application code; test output goes to a temp folder, never to reports/hw08/raw.

  1. required files exist
  2. starts the docker compose stack (apache/kafka + worker + FastAPI on PORT_BASE) if the broker or API is not up
  3. Part 1: topics exist; CREATE_ENTITY -> GET_ENTITY round-trips through Kafka (HTTP and direct client); errors are clean;
     the correlation_id is preserved; the request message on the topic has the four required fields
  4. Part 2: Planner/Writer/Reviewer as separate processes with the REAL model (qwen3:8b); one question goes inbox -> final
     and the same correlation_id appears in all four topics
  5. Part 3 (Writer in model-free stub mode): replay with idempotency, Writer killed mid-work and restarted, poison message
     -> dead-letter topic, 20 keyed messages keep their order; the naive replay is also run to show the check can fail
  6. ruff

Checks test behaviour (counts, offsets, topics), not wording. Needs Docker Desktop and Ollama with qwen3:8b.
Run from the repo root, inside the venv:   python verify_hw08.py        (--fast skips the real-model check and the kill test)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
KAFKA_DIR = REPO_ROOT / "code" / "kafka_hw8"
HW08 = REPO_ROOT / "reports" / "hw08"
VERIFICATION_OUTPUT = HW08 / "verification.json"
SID4, SEED, VERIFY_SEED, PORT_BASE, PREFIX = "9871", "9871", "269871", 8871, "s9871"
BASE_URL = f"http://127.0.0.1:{PORT_BASE}"
MODEL_CONFIG = ("Part 1/3: no model (Writer in WRITER_MODE=stub for the failure tests); Part 2: qwen3:8b via Ollama "
                "(thinking off, temperature 0.3/0.5, sampling seed = SEED 9871); Kafka: apache/kafka:3.9.0 single node (KRaft); "
                "client: confluent-kafka; FastAPI on port 8871")
REQUIRED_FILES = [
    "verify_hw08.py", "docker-compose.yml",
    *(f"code/kafka_hw8/{f}" for f in ("common.py", "worker.py", "kafka_rpc.py", "api.py", "homework_demo.py", "agent_common.py",
                                      "planner.py", "writer.py", "reviewer.py", "send_question.py", "failure_tests.py",
                                      "summarize_part3.py", "Dockerfile", "requirements.txt")),
    "reports/hw08/RUN_LOG.txt", "reports/hw08/METRICS.md", "reports/hw08/raw/part3_ordering_messages.json",
    "reports/hw08/raw/part3_ordering_unkeyed.csv", "reports/hw08/raw/part3_ordering_keyed.csv",
]
REQUEST_TOPIC, RESPONSE_TOPIC = f"{PREFIX}_entity_requests", f"{PREFIX}_entity_responses"
PIPELINE_TOPICS = {f"{PREFIX}_inbox": 1, f"{PREFIX}_tasks": 2, f"{PREFIX}_drafts": 1, f"{PREFIX}_final": 1}
FIXTURE = {"fixture_name": "Verify Lions vs Verify Tigers", "teams_players": "Lions; Tigers", "submitter_email": "v@example.com",
           "description": "verify_hw08 smoke test", "category": "Cricket", "agree_terms": True}

sys.path.insert(0, str(KAFKA_DIR))
tmp = Path(tempfile.mkdtemp(prefix="verify_hw08_"))
state = {"started_stack": False}


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=20, cwd=str(REPO_ROOT)).stdout.rstrip("\n")
    except Exception:
        return ""


def check(name, fn):
    t0 = time.time()
    try:
        passed, detail = fn()
        return {"check": name, "passed": bool(passed), "detail": detail, "seconds": round(time.time() - t0, 1)}
    except Exception as e:
        return {"check": name, "passed": False, "detail": f"Exception: {type(e).__name__}: {e}", "seconds": round(time.time() - t0, 1)}


def broker_up():
    from confluent_kafka.admin import AdminClient
    try:
        AdminClient({"bootstrap.servers": "localhost:9092"}).list_topics(timeout=5)
        return True
    except Exception:
        return False


def api_up():
    try:
        return requests.get(BASE_URL + "/health", timeout=2).status_code == 200
    except Exception:
        return False


def start_stack_if_needed():
    if broker_up() and api_up():
        return
    state["started_stack"] = True
    subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=str(REPO_ROOT), capture_output=True, timeout=600)
    for _ in range(90):
        if broker_up() and api_up():
            break
        time.sleep(2)
    time.sleep(8)  # let the worker join its consumer group


def post(path, body, headers=None):
    return requests.post(BASE_URL + path, json=body, headers=headers or {}, timeout=30)


# ---------------------------------------------------------------- checks

def check_files():
    missing = [f for f in REQUIRED_FILES if not (REPO_ROOT / f).exists()]
    return not missing, f"All {len(REQUIRED_FILES)} required files present." if not missing else f"MISSING: {missing}"


def check_stack():
    from confluent_kafka.admin import AdminClient
    topics = AdminClient({"bootstrap.servers": "localhost:9092"}).list_topics(timeout=10).topics
    need = [REQUEST_TOPIC, RESPONSE_TOPIC, *PIPELINE_TOPICS, f"{PREFIX}_dead_letter"]
    missing = [t for t in need if t not in topics]
    tasks_parts = len(topics[f"{PREFIX}_tasks"].partitions) if f"{PREFIX}_tasks" in topics else 0
    names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    running = [n for n in ("s9871-kafka", "s9871-worker", "s9871-api") if n in names]
    ok = not missing and tasks_parts == 2 and len(running) == 3 and api_up()
    return ok, f"containers running {running}; topics missing {missing}; {PREFIX}_tasks partitions={tasks_parts}; API health {api_up()}"


def check_p1_roundtrip():
    r1 = post("/fixtures", FIXTURE)
    b1 = r1.json()
    eid = b1.get("entity_id", "")
    is_uuid = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", eid))
    r2 = requests.get(f"{BASE_URL}/fixtures/{eid}", timeout=30)
    b2 = r2.json()
    entity = b2.get("entity", {})
    same = {k: v for k, v in entity.items() if k != "entity_id"} == FIXTURE and entity.get("entity_id") == eid
    ok = (r1.status_code == 200 and b1.get("success") is True and b1.get("message") == "Entity created" and is_uuid
          and r2.status_code == 200 and b2.get("success") is True and same
          and b1["correlation_id"] == r1.headers.get("X-Correlation-ID") and b2["correlation_id"] == r2.headers.get("X-Correlation-ID")
          and b1["correlation_id"] != b2["correlation_id"])
    return ok, f"CREATE {r1.status_code} success={b1.get('success')} uuid={is_uuid}; GET {r2.status_code} success={b2.get('success')} fields equal={same}"


def check_p1_errors():
    out = []
    nf = requests.get(f"{BASE_URL}/fixtures/{uuid.uuid4()}", timeout=30)
    out.append(("unknown id", nf.status_code == 404 and nf.json()["success"] is False and nf.json()["error"] == "Entity not found"
                and nf.json()["correlation_id"] == nf.headers["X-Correlation-ID"]))
    uo = post("/kafka/request", {"operation": "DELETE_ENTITY", "data": {}}, {"X-Correlation-ID": "verify-unknown-op"})
    out.append(("unknown operation", uo.json() == {"correlation_id": "verify-unknown-op", "success": False, "error": "Unknown operation"}))
    bad = {"email": {**FIXTURE, "submitter_email": "nope"}, "empty name": {**FIXTURE, "fixture_name": "   "},
           "missing field": {k: v for k, v in FIXTURE.items() if k != "description"}, "unknown field": {**FIXTURE, "x": 1},
           "bad category": {**FIXTURE, "category": "Chess"}, "terms false": {**FIXTURE, "agree_terms": False}}
    for label, body in bad.items():
        r = post("/fixtures", body)
        j = r.json()
        out.append((label, r.status_code == 400 and j.get("success") is False and bool(j.get("error")) and bool(j.get("correlation_id"))))
    failed = [n for n, ok in out if not ok]
    return not failed, f"{len(out) - len(failed)}/{len(out)} error paths clean (404 not found, unknown operation, 6 invalid creates); failed: {failed}"


def check_p1_kafka_level():
    import failure_tests as ft
    from common import setup_logging
    from kafka_rpc import KafkaRpcClient
    ft.console = open(os.devnull, "w")
    client = KafkaRpcClient(setup_logging("verify"))
    try:
        corr = f"verify-corr-{uuid.uuid4().hex[:8]}"
        resp = client.request("CREATE_ENTITY", FIXTURE, correlation_id=corr)
    finally:
        client.close()
    sent = [r["value"] for r in ft.read_topic(REQUEST_TOPIC) if r["value"].get("correlation_id") == corr]
    got = [r["value"] for r in ft.read_topic(RESPONSE_TOPIC) if r["value"].get("correlation_id") == corr]
    shape = bool(sent) and set(sent[0]) == {"correlation_id", "reply_to", "operation", "data"} and sent[0]["reply_to"] == RESPONSE_TOPIC
    ok = resp.get("correlation_id") == corr and resp.get("success") is True and shape and len(got) == 1
    return ok, f"response corr preserved={resp.get('correlation_id') == corr}; request on topic has 4 required fields, reply_to={RESPONSE_TOPIC}: {shape}; responses on topic: {len(got)}"


def check_p2_pipeline():
    import failure_tests as ft
    ft.console = open(os.devnull, "w")
    ft.TOPIC_PARTITIONS.clear()
    ft.TOPIC_PARTITIONS.update({**PIPELINE_TOPICS, f"{PREFIX}_dead_letter": 1})
    ft.reset_topics()
    suffix = f"_verify_{uuid.uuid4().hex[:6]}"
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "HW8_GROUP_SUFFIX": suffix, "HW8_STATE_DIR": str(tmp / "p2state"), "HW8_MODE": "fixed"}
    procs = [subprocess.Popen([sys.executable, "-u", f"{a}.py"], cwd=KAFKA_DIR, env=env, stdout=open(tmp / f"p2_{a}.log", "wb"),
                              stderr=subprocess.STDOUT) for a in ("planner", "writer", "reviewer")]
    try:
        time.sleep(15)
        r = subprocess.run([sys.executable, "send_question.py", "What should a league office check before scheduling a fixture?"],
                           cwd=KAFKA_DIR, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    finally:
        for p in procs:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    m = re.search(r"corr=(\S+)", r.stdout)
    corr = m.group(1) if m else ""
    final = json.loads(r.stdout[r.stdout.index("{\n"):r.stdout.rindex("}") + 1]) if "{\n" in r.stdout else {}
    seen = {t: sum(1 for x in ft.read_topic(t) if x["value"].get("correlation_id") == corr) for t in PIPELINE_TOPICS}
    ok = (r.returncode == 0 and final.get("correlation_id") == corr and final.get("status") in ("approved", "rejected")
          and len(final.get("answer", "").split()) >= 5 and all(n >= 1 for n in seen.values()))
    return ok, f"final status={final.get('status')!r}, answer words={len(final.get('answer', '').split())}, same correlation_id in topics {seen}"


def run_scenario(scenario, mode):
    env = {**os.environ, "HW8_RAW_DIR": str(tmp / "raw")}
    r = subprocess.run([sys.executable, "failure_tests.py", scenario, "--mode", mode], cwd=KAFKA_DIR, env=env, capture_output=True,
                       text=True, encoding="utf-8", timeout=300)
    return json.loads((tmp / "raw" / f"part3_{scenario}_{mode}.json").read_text(encoding="utf-8")), r


def check_p3_duplicate():
    naive, _ = run_scenario("duplicate", "naive")
    fixed, _ = run_scenario("duplicate", "fixed")
    ok = (naive["drafts_in_output_topic"] == 2 and fixed["drafts_in_output_topic"] == 1 and fixed["writer_work_executions"] == 1
          and fixed["duplicate_skips_logged"] == 1 and fixed["lag"]["0"]["lag"] == 0)
    return ok, f"naive replay -> {naive['drafts_in_output_topic']} drafts; with idempotency -> {fixed['drafts_in_output_topic']} draft, {fixed['writer_work_executions']} work run, lag {fixed['lag']['0']['lag']}"


def check_p3_kill():
    d, _ = run_scenario("kill", "fixed")
    ok = (d["after_kill"]["committed"]["0"] is None and d["after_kill"]["drafts"] == 0 and d["redelivered_after_restart"]
          and d["drafts_in_output_topic"] == 1 and d["final_lag"]["0"]["committed"] == 1)
    return ok, f"offset uncommitted at kill: {d['after_kill']['committed']['0'] is None}; redelivered after restart: {d['redelivered_after_restart']}; drafts {d['drafts_in_output_topic']}; committed after success: {d['final_lag']['0']['committed']}"


def check_p3_poison():
    d, _ = run_scenario("poison", "fixed")
    ok = (d["poison_attempts_logged"] == 3 and d["dead_letter_messages_for_poison"] == 1 and d["good_message_processed"]
          and d["lag"]["0"]["lag"] == 0)
    return ok, f"attempts {d['poison_attempts_logged']}, dead-letter messages {d['dead_letter_messages_for_poison']}, good message processed {d['good_message_processed']}, lag {d['lag']['0']['lag']}"


def check_p3_ordering():
    d, _ = run_scenario("ordering", "keyed")
    ok = d["messages_processed"] == 20 and d["entities_out_of_order"] == 0 and d["entities_split_across_partitions"] == 0
    return ok, f"{d['messages_processed']} messages processed, entities out of order {d['entities_out_of_order']}, entities split across partitions {d['entities_split_across_partitions']}"


def check_ruff():
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "code/kafka_hw8", "verify_hw08.py"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode == 0, (r.stdout.strip().splitlines() or [""])[-1][:200]


def main():
    fast = "--fast" in sys.argv
    started = datetime.now().isoformat(timespec="seconds")
    print("verify_hw08 run at", started, flush=True)
    checks = []
    c = check("required files exist", check_files)
    print(f"... {c['check']}\n    [{'PASS' if c['passed'] else 'FAIL'}] {c['detail'][:300]}", flush=True)
    checks.append(c)
    try:
        start_stack_if_needed()
        plan = [("Stack: Kafka + worker + FastAPI running, all topics exist, tasks has 2 partitions", check_stack),
                ("Part 1: CREATE_ENTITY then GET_ENTITY round-trip through Kafka via the API (uuid, same fields, correlation_id preserved)", check_p1_roundtrip),
                ("Part 1: clean errors (unknown id, unknown operation, invalid fields) each carry a correlation_id", check_p1_errors),
                ("Part 1: direct Kafka client - request has correlation_id/reply_to/operation/data, response echoes the correlation_id", check_p1_kafka_level),
                ("Part 2: Planner, Writer, Reviewer as separate processes (real model) - one question reaches final with the same correlation_id in all four topics", check_p2_pipeline),
                ("Part 3: duplicate replay - 2 drafts without idempotency, 1 with it", check_p3_duplicate),
                ("Part 3: Writer killed mid-work - offset uncommitted, message redelivered after restart, committed only after success", check_p3_kill),
                ("Part 3: poison message - 3 attempts, then dead-letter topic, next message still processed", check_p3_poison),
                ("Part 3: 20 messages (VERIFY_SEED) keyed by entity stay in one partition and in order", check_p3_ordering)]
        for name, fn in plan:
            if fast and fn in (check_p2_pipeline, check_p3_kill):
                continue
            print(f"... {name}", flush=True)
            r = check(name, fn)
            print(f"    [{'PASS' if r['passed'] else 'FAIL'}] {r['detail'][:300]}", flush=True)
            checks.append(r)
        r = check("Ruff passes on the HW8 code", check_ruff)
        print(f"... {r['check']}\n    [{'PASS' if r['passed'] else 'FAIL'}] {r['detail']}", flush=True)
        checks.append(r)
    finally:
        if state["started_stack"]:
            subprocess.run(["docker", "compose", "stop"], cwd=str(REPO_ROOT), capture_output=True)
    passed = sum(c["passed"] for c in checks)
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if not ln.startswith("??") and "__pycache__" not in ln]
    out = {"homework": 8, "sid4": SID4, "commit_hash": git("rev-parse", "HEAD"), "tracked_files_modified_since_commit": dirty,
           "model_config": MODEL_CONFIG, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "port_base": PORT_BASE, "run_at": started,
           "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    VERIFICATION_OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"\n{passed}/{len(checks)} checks passed -> {VERIFICATION_OUTPUT}")
    sys.exit(0 if out["all_passed"] else 1)


if __name__ == "__main__":
    main()
