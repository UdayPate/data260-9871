"""
DATA-260 Homework 6 - Part 4.6: does each memory system survive a server restart?
  python persistence_probe.py before <out.json>   snapshot + create an un-saved conversation turn
  (restart the server)
  python persistence_probe.py after  <out.json>   snapshot again, then compare with the 'before' file
File memory (MEMORY.md) and Mongo memory (messages/summaries/episodes for uday_demo) are both snapshotted
through the HTTP API; the in-process recent-conversation buffer that /dream reads is probed too.
"""

import hashlib
import json
import sys
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8871"
h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def snapshot() -> dict:
    fm = requests.get(f"{BASE}/api/file-memory").json()
    mem_out = requests.post(f"{BASE}/api/file-chat", json={"message": "/memory"}).json()["output"]
    mongo = requests.get(f"{BASE}/api/memory/uday_demo").json()
    agg = requests.get(f"{BASE}/api/aggregate/uday_demo").json()
    return {"file_memory_entries": fm["entries"], "file_memory_last_consolidated": fm["last_consolidated"],
            "file_memory_text_hash": h(mem_out),
            "mongo_messages_returned": len(mongo["messages"]), "mongo_episodes_returned": len(mongo["episodes"]),
            "mongo_lifetime_summary_hash": h(json.dumps(mongo["latest_lifetime_summary"], sort_keys=True)),
            "mongo_daily_counts": agg["daily_message_counts"],
            "mongo_state_hash": h(json.dumps(mongo, sort_keys=True))}


if __name__ == "__main__":
    phase, out = sys.argv[1], Path(sys.argv[2])
    if phase == "before":
        snap = snapshot()
        r = requests.post(f"{BASE}/api/file-chat", json={"message": "Remember that my locker number is seventeen."}, timeout=300).json()
        snap["before_restart_chat_reply"] = r["reply"]
        out.write_text(json.dumps(snap, indent=1), encoding="utf-8")
        print("BEFORE restart:", json.dumps({k: v for k, v in snap.items() if k != "before_restart_chat_reply"}, indent=1))
    else:
        before = json.loads(out.read_text(encoding="utf-8"))
        snap = snapshot()
        dream = requests.post(f"{BASE}/api/file-chat", json={"message": "/dream"}, timeout=300).json()["output"]
        print("AFTER restart:", json.dumps(snap, indent=1))
        same = {k: before[k] == snap[k] for k in snap}
        print("\nidentical after restart:", json.dumps(same, indent=1))
        print("\n/dream right after restart (needs the in-process conversation buffer):", dream)
        ok = all(same.values()) and "no recent conversation" in dream
        print("\nRESULT:", "file facts + Mongo memory persisted; un-saved conversation buffer was lost" if ok else "UNEXPECTED")
        sys.exit(0 if ok else 1)
