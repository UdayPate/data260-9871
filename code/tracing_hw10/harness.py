"""HW10 helper: start/stop the HW8 Planner, Writer and Reviewer as host processes (same approach as HW9's run_part2.start_agents, but it also returns the
environment so a single agent can be restarted into the same consumer group)."""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

KAFKA_DIR = Path(__file__).resolve().parents[1] / "kafka_hw8"
sys.path.insert(0, str(KAFKA_DIR))


def kill(proc) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


def wait_ready(log: Path, secs: float = 90) -> bool:
    end = time.time() + secs
    while time.time() < end:
        if log.exists() and "ready and listening" in log.read_text(errors="replace"):
            return True
        time.sleep(0.5)
    return False


def spawn(name: str, env: dict, log: Path):
    return subprocess.Popen([sys.executable, "-u", f"{name}.py"], cwd=KAFKA_DIR, env=env, stdout=open(log, "wb"), stderr=subprocess.STDOUT)


def start_agents(out_dir: Path, tag: str = "part4", extra_env: dict | None = None):
    """Resets the pipeline topics, starts planner/writer/reviewer, waits until all listen. Returns ({name: Popen}, env)."""
    import failure_tests as ft  # HW8 harness: reuse its topic reset
    ft.console = open(os.devnull, "w")
    ft.TOPIC_PARTITIONS.clear()
    ft.TOPIC_PARTITIONS.update({"s9871_inbox": 1, "s9871_tasks": 2, "s9871_drafts": 1, "s9871_final": 1, "s9871_dead_letter": 1})
    ft.reset_topics()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "HW8_MODE": "fixed", "HW8_GROUP_SUFFIX": f"_hw10_{uuid.uuid4().hex[:6]}",
           "HW8_STATE_DIR": tempfile.mkdtemp(prefix="hw10_agents_"), **(extra_env or {})}
    logs = {n: out_dir / f"{tag}_agent_{n}.log" for n in ("planner", "writer", "reviewer")}
    procs = {n: spawn(n, env, logs[n]) for n in logs}
    for n in logs:
        wait_ready(logs[n])
    return procs, env
