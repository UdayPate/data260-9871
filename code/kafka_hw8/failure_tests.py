"""
DATA-260 Homework 8 Part 3 - failure tests against the real Kafka broker and real Writer processes.

    python failure_tests.py duplicate|kill|poison|ordering  --mode naive|fixed     (ordering: unkeyed|keyed)

Each run resets the topics it uses, starts real Writer processes (WRITER_MODE=stub: model-free, so the tests
are fast and the timings come from the messages' own work_s), injects the failure, and writes
  reports/hw08/raw/part3_<scenario>_<mode>.json   what was observed (the numbers the report uses)
  reports/hw08/raw/part3_<scenario>_<mode>_console.txt   this script's own timestamped output
  reports/hw08/raw/part3_<scenario>_<mode>_writer*.log  each Writer's real log
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from agent_common import DEAD_LETTER, DRAFTS, TASKS
from common import BOOTSTRAP, PREFIX

HERE = Path(__file__).resolve().parent
RAW = Path(os.environ.get("HW8_RAW_DIR", HERE.parents[1] / "reports" / "hw08" / "raw"))  # verify_hw08.py redirects this
SEED, VERIFY_SEED = 9871, 269871
TOPIC_PARTITIONS = {TASKS: 2, DRAFTS: 1, DEAD_LETTER: 1}

console = None


def say(text: str = "") -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3] + f" [harness] {text}"
    print(line, flush=True)
    console.write(line + "\n")
    console.flush()


def reset_topics() -> None:
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    old = [t for t in TOPIC_PARTITIONS if t in admin.list_topics(timeout=15).topics]
    for fut in admin.delete_topics(old).values():
        fut.result()
    for _ in range(60):  # deletion finishes asynchronously on the broker
        if not set(old) & set(admin.list_topics(timeout=15).topics):
            break
        time.sleep(0.5)
    for _ in range(30):
        missing = [t for t in TOPIC_PARTITIONS if t not in admin.list_topics(timeout=15).topics]
        if not missing:
            break
        for fut in admin.create_topics([NewTopic(t, TOPIC_PARTITIONS[t], 1) for t in missing]).values():
            try:
                fut.result()
            except Exception:  # noqa: BLE001 - e.g. still marked for deletion: just try again
                time.sleep(1)
    say("topics reset: " + ", ".join(f"{t}({n} partition{'s' if n > 1 else ''})" for t, n in TOPIC_PARTITIONS.items()))


class Writer:
    """A real writer.py process with its own log file."""

    def __init__(self, tag: str, group_suffix: str, state_dir: Path, log_path: Path, env: dict):
        self.tag, self.log_path = tag, log_path
        full = {**os.environ, "PYTHONUNBUFFERED": "1", "WRITER_MODE": "stub", "HW8_INSTANCE": tag,
                "HW8_GROUP_SUFFIX": group_suffix, "HW8_STATE_DIR": str(state_dir), **env}
        self.out = open(log_path, "wb")
        self.proc = subprocess.Popen([sys.executable, "-u", "writer.py"], cwd=HERE, env=full, stdout=self.out,
                                     stderr=subprocess.STDOUT)
        say(f"started Writer {tag} pid={self.proc.pid} env={env}")

    def text(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def wait_for(self, pattern: str, timeout: float = 60) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if re.search(pattern, self.text()):
                return True
            time.sleep(0.2)
        return False

    def kill(self) -> None:
        """Hard kill (no SIGTERM handler, no consumer.close): what a crashed process looks like to the broker."""
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
        self.proc.wait()
        self.out.close()
        say(f"HARD-KILLED Writer {self.tag} pid={self.proc.pid}")

    def stop(self) -> None:
        if self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            self.proc.wait()
        self.out.close()


def read_topic(topic: str) -> list[dict]:
    """Every message currently in the topic, in (partition, offset) order."""
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"reader-{uuid.uuid4().hex[:8]}",
                         "enable.auto.commit": False})
    parts = consumer.list_topics(topic, timeout=15).topics[topic].partitions
    ends = {}
    for p in parts:
        low, high = consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=15)
        ends[p] = high
    consumer.assign([TopicPartition(topic, p, 0) for p in parts])
    rows, remaining = [], {p for p, high in ends.items() if high > 0}
    end = time.time() + 20
    while remaining and time.time() < end:
        msg = consumer.poll(0.5)
        if msg is None or msg.error():
            continue
        rows.append({"partition": msg.partition(), "offset": msg.offset(), "key": (msg.key() or b"").decode(),
                     "value": json.loads(msg.value())})
        if msg.offset() + 1 >= ends[msg.partition()]:
            remaining.discard(msg.partition())
    consumer.close()
    return sorted(rows, key=lambda r: (r["partition"], r["offset"]))


def committed(group: str) -> dict:
    """Committed offset of the tasks topic per partition for a consumer group (None = nothing committed)."""
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "enable.auto.commit": False})
    parts = consumer.list_topics(TASKS, timeout=15).topics[TASKS].partitions
    result = {}
    for tp in consumer.committed([TopicPartition(TASKS, p) for p in parts], timeout=15):
        result[tp.partition] = tp.offset if tp.offset >= 0 else None
    consumer.close()
    return result


def lag(group: str) -> dict:
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "enable.auto.commit": False})
    out = {}
    for p, off in committed(group).items():
        _, high = consumer.get_watermark_offsets(TopicPartition(TASKS, p), timeout=15)
        out[p] = {"committed": off, "log_end": high, "lag": high - (off or 0)}
    consumer.close()
    return out


def produce(messages: list[tuple], flush: bool = True) -> list[dict]:
    """messages: (key, payload_dict_or_bytes, partition_or_None). Returns where each one landed."""
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    landed = []

    def done(err, msg):
        landed.append({"partition": msg.partition(), "offset": msg.offset(), "key": (msg.key() or b"").decode()})

    for key, payload, partition in messages:
        value = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        kwargs = {"partition": partition} if partition is not None else {}
        producer.produce(TASKS, key=key, value=value, on_delivery=done, **kwargs)
    producer.flush(15)
    return landed


def wait_until(check, timeout: float, what: str) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.5)
    say(f"timed out after {timeout:.0f}s waiting for: {what}")
    return False


def task(corr: str, **extra) -> dict:
    return {"correlation_id": corr, "question": f"Fixture task {corr}",
            "plan": ["check the field", "check the referees", "confirm the teams"], **extra}


def count(topic_rows: list[dict], corr: str) -> int:
    return sum(1 for r in topic_rows if r["value"].get("correlation_id") == corr)


# ---------------------------------------------------------------- scenarios

def run_duplicate(mode: str, ctx: dict) -> dict:
    """I. Same message (same correlation_id, same bytes) delivered twice to the Writer."""
    w = Writer("A", ctx["suffix"], ctx["state"], ctx["log"]("writer"), {"HW8_MODE": mode})
    w.wait_for("ready and listening")
    corr = f"dup-{mode}-{uuid.uuid4().hex[:6]}"
    payload = json.dumps(task(corr)).encode()
    say(f"sending the original message corr={corr}")
    produce([(corr, payload, 0)])
    wait_until(lambda: count(read_topic(DRAFTS), corr) >= 1, 30, "first draft")
    say("REPLAYING the identical message (same correlation_id, same bytes)")
    produce([(corr, payload, 0)])
    wait_until(lambda: w.text().count("RECEIVED") >= 2, 30, "Writer to receive the replay")
    time.sleep(4 if mode == "naive" else 2)
    drafts = [r for r in read_topic(DRAFTS) if r["value"].get("correlation_id") == corr]
    text = w.text()
    result = {"correlation_id": corr, "deliveries_received": text.count("RECEIVED"),
              "writer_work_executions": text.count("WORK start"), "duplicate_skips_logged": text.count("DUPLICATE"),
              "drafts_in_output_topic": len(drafts), "lag": lag(f"{PREFIX}_writers{ctx['suffix']}")}
    w.stop()
    return result


def run_kill(mode: str, ctx: dict) -> dict:
    """II. Hard-kill the Writer mid-processing, restart it, see whether the message survives."""
    group = f"{PREFIX}_writers{ctx['suffix']}"
    w1 = Writer("A", ctx["suffix"], ctx["state"], ctx["log"]("writer_1_killed"), {"HW8_MODE": mode})
    w1.wait_for("ready and listening")
    corr = f"kill-{mode}-{uuid.uuid4().hex[:6]}"
    say(f"sending corr={corr} (work_s=8, so the Writer is busy for 8 s)")
    produce([(corr, task(corr, work_s=8), 0)])
    w1.wait_for(f"WORK start corr={corr}", 30)
    time.sleep(1.5)
    w1.kill()
    after_kill = {"committed": committed(group), "drafts": count(read_topic(DRAFTS), corr)}
    say(f"right after the kill: committed offsets={after_kill['committed']} drafts_for_corr={after_kill['drafts']}")
    w2 = Writer("A", ctx["suffix"], ctx["state"], ctx["log"]("writer_2_restarted"), {"HW8_MODE": mode})
    redelivered = w2.wait_for(f"RECEIVED .*corr={corr}", 40)
    done = wait_until(lambda: count(read_topic(DRAFTS), corr) >= 1, 30 if mode == "fixed" else 20, "a draft after restart")
    time.sleep(1)
    result = {"correlation_id": corr, "after_kill": after_kill, "redelivered_after_restart": redelivered,
              "draft_produced_after_restart": done, "drafts_in_output_topic": count(read_topic(DRAFTS), corr),
              "final_lag": lag(group)}
    w2.stop()
    return result


def run_poison(mode: str, ctx: dict) -> dict:
    """III. A message the Writer cannot process, followed by a good one on the same partition."""
    env = {"HW8_MODE": mode}
    if mode == "naive":
        env["HW8_COMMIT"] = "after"  # isolate the retry policy: the naive Writer commits after success, retries forever
    w = Writer("A", ctx["suffix"], ctx["state"], ctx["log"]("writer"), env)
    w.wait_for("ready and listening")
    bad, good = f"poison-{mode}-{uuid.uuid4().hex[:6]}", f"good-{mode}-{uuid.uuid4().hex[:6]}"
    poison = task(bad)
    poison["plan"] = None  # valid JSON, but the Writer's validation rejects it every time
    say(f"sending poison corr={bad} then good corr={good}, both to partition 0")
    produce([(bad, poison, 0), (good, task(good), 0)])
    if mode == "fixed":
        wait_until(lambda: count(read_topic(DRAFTS), good) >= 1 and count(read_topic(DEAD_LETTER), bad) >= 1, 40,
                   "poison dead-lettered and good message processed")
    else:
        time.sleep(15)
    text = w.text()
    dead = [r["value"] for r in read_topic(DEAD_LETTER) if r["value"]["correlation_id"] == bad]
    result = {"poison_corr": bad, "good_corr": good,
              "poison_attempts_logged": len(re.findall(rf"ATTEMPT .* corr={bad}", text)),
              "dead_letter_messages_for_poison": len(dead), "dead_letter_attempts_field": [d["attempts"] for d in dead],
              "good_message_processed": count(read_topic(DRAFTS), good) >= 1,
              "lag": lag(f"{PREFIX}_writers{ctx['suffix']}")}
    w.stop()
    return result


def gen_ordering_messages() -> list[dict]:
    """20 related messages (4 fixtures, several updates each) from VERIFY_SEED. Same list for both runs."""
    rng = random.Random(VERIFY_SEED)
    entities = [f"FX-9871-{n}" for n in (101, 102, 103, 104)]
    seq = dict.fromkeys(entities, 0)
    out = []
    for i in range(1, 21):
        e = rng.choice(entities)
        seq[e] += 1
        out.append(task(f"ord-{i:02d}", entity_id=e, entity_seq=seq[e], send_index=i, work_s=round(rng.uniform(0.1, 0.8), 2)))
    return out


def run_ordering(mode: str, ctx: dict) -> dict:
    """IV. 20 related messages, two partitions, two Writers in one group. mode = unkeyed | keyed."""
    messages = gen_ordering_messages()
    (RAW / "part3_ordering_messages.json").write_text(json.dumps(
        {"VERIFY_SEED": VERIFY_SEED, "messages": messages}, indent=2), encoding="utf-8")
    a = Writer("A", ctx["suffix"], ctx["state"], ctx["log"]("writer_A"), {"HW8_MODE": "fixed"})
    b = Writer("B", ctx["suffix"], ctx["state"], ctx["log"]("writer_B"), {"HW8_MODE": "fixed"})

    def settled() -> bool:  # each Writer's latest assignment is exactly one partition (group has rebalanced)
        mine = [re.findall(r"Assigned partitions: \[([\d, ]*)\]", w.text()) for w in (a, b)]
        return all(m and len(m[-1].split(",")) == 1 for m in mine) and mine[0][-1] != mine[1][-1]

    wait_until(settled, 60, "both Writers to hold one partition each")
    say("assignments: " + "; ".join(f"{w.tag}={re.findall(r'Assigned partitions: (.*)', w.text())[-1]}" for w in (a, b)))
    keyed = mode == "keyed"
    say(f"sending 20 messages, key={'entity_id' if keyed else 'none (null key)'}")
    landed = produce([(m["entity_id"] if keyed else None, m, None) for m in messages])
    wait_until(lambda: len(read_topic(DRAFTS)) >= 20, 90, "all 20 drafts")
    time.sleep(1)
    rows = []
    for w in (a, b):
        for ts, corr, part, off, ent, seq in re.findall(
                r"^(\S+ \S+) \[writer-\w\] PROCESSED corr=(\S+) partition=(\d+) offset=(\d+) entity=(\S+) seq=(\d+)",
                w.text(), re.M):
            rows.append({"processed_at": ts, "writer": w.tag, "corr": corr, "partition": int(part), "offset": int(off),
                         "entity_id": ent, "entity_seq": int(seq)})
    rows.sort(key=lambda r: r["processed_at"])
    for i, r in enumerate(rows, 1):
        r["processing_order"] = i
    per_entity = {}
    for e in sorted({r["entity_id"] for r in rows}):
        mine = [r for r in rows if r["entity_id"] == e]
        order = [r["entity_seq"] for r in mine]
        inv = sum(1 for i in range(len(order)) for j in range(i + 1, len(order)) if order[i] > order[j])
        per_entity[e] = {"messages": len(mine), "processed_in_seq_order": order, "inversions": inv,
                         "partitions": sorted({r["partition"] for r in mine}), "writers": sorted({r["writer"] for r in mine})}
    csv = ["processing_order,processed_at,writer,corr,partition,offset,entity_id,entity_seq"] + [
        ",".join(str(r[k]) for k in ("processing_order", "processed_at", "writer", "corr", "partition", "offset",
                                     "entity_id", "entity_seq")) for r in rows]
    (RAW / f"part3_ordering_{mode}.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")
    a.stop()
    b.stop()
    return {"messages_processed": len(rows), "partition_of_each_send": [x["partition"] for x in landed],
            "per_entity": per_entity, "entities_out_of_order": sum(1 for v in per_entity.values() if v["inversions"]),
            "total_inversions": sum(v["inversions"] for v in per_entity.values()),
            "entities_split_across_partitions": sum(1 for v in per_entity.values() if len(v["partitions"]) > 1)}


SCENARIOS = {"duplicate": run_duplicate, "kill": run_kill, "poison": run_poison, "ordering": run_ordering}


def main() -> int:
    global console
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=SCENARIOS)
    ap.add_argument("--mode", required=True)
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    stem = f"part3_{args.scenario}_{args.mode}"
    console = open(RAW / f"{stem}_console.txt", "w", encoding="utf-8")
    suffix = f"_{args.scenario}_{args.mode}_{uuid.uuid4().hex[:6]}"
    state = HERE / "state" / suffix.strip("_")
    ctx = {"suffix": suffix, "state": state, "log": lambda n: RAW / f"{stem}_{n}.log"}
    say(f"scenario={args.scenario} mode={args.mode} SEED={SEED} VERIFY_SEED={VERIFY_SEED} consumer-group suffix={suffix}")
    reset_topics()
    result = SCENARIOS[args.scenario](args.mode, ctx)
    result = {"scenario": args.scenario, "mode": args.mode, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
              "writer_mode": "stub (model-free)", "finished_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}", **result}
    (RAW / f"{stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    say("RESULT " + json.dumps({k: v for k, v in result.items() if k != "per_entity"}))
    reset_topics()  # leave no test messages behind in the topics the real Part 2 pipeline uses
    console.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
