"""
DATA-260 Homework 6 - Part 2 live test. Sends a 12-message conversation to the
running API (real Ollama model, real MongoDB), prints each reply and what memory
was used, exercises failure paths, then verifies persistence directly in MongoDB.
Usage: python test_part2.py [user_id]    (server must be running on 8871)
"""

import sys
from datetime import datetime

import requests
from pymongo import MongoClient

BASE = "http://127.0.0.1:8871"
USER = sys.argv[1] if len(sys.argv) > 1 else "uday_demo"
results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


db = MongoClient("mongodb://localhost:27017", tz_aware=True)["s9871_doc"]
for coll in ("messages", "summaries", "episodes"):
    db[coll].delete_many({"user_id": USER})   # deterministic reruns (test user only)

print("Run at", datetime.now().isoformat(timespec="seconds"), "| user:", USER)
print("settings:", requests.get(f"{BASE}/api/settings").json())

CONVO = [
    "Hi! I'm Uday and I coach the Milpitas Lions, a U12 soccer team.",
    "We usually play on Saturday mornings at Cesar Chavez Park.",
    "Our team colors are green and white.",
    "Can you remind me what kind of team I coach?",
    "My assistant coach is Priya and she can't make games in November.",
    "I'm allergic to peanuts, so please no peanut snacks at team events.",
    "What day do we usually play?",
    "We have a tough rival: the San Jose Tigers, who play on Sundays.",
    "Our next fixture is on November 1st at 6pm against the Tigers.",
    "Who is my assistant coach and when is she unavailable?",
    "Please remember I prefer email reminders over text messages.",
    "What do you remember about me and my team?",
]

session = None
last = None
for i, msg in enumerate(CONVO, 1):
    r = requests.post(f"{BASE}/api/chat", json={"user_id": USER, "session_id": session, "message": msg}
                      if session else {"user_id": USER, "message": msg}, timeout=300)
    if r.status_code != 200:
        print(f"turn {i}: HTTP {r.status_code} {r.text[:300]}")
        check(f"turn {i} returns 200", False)
        continue
    last = r.json()
    session = last["session_id"]
    mu, mw, u = last["memory_used"], last["memory_written"], last["usage"]
    print(f"\n--- turn {i} ---\nUSER     : {msg}\nASSISTANT: {last['reply']}")
    print(f"  used   : short_term={mu['short_term_count']} "
          f"session_summary={'yes' if mu['session_summary'] else 'no'} "
          f"lifetime={'yes' if mu['long_term_summary'] else 'no'} "
          f"episodes={[e['fact'] for e in mu['episodic_facts']]}")
    print(f"  wrote  : new_episodes={[e['fact'] for e in mw['new_episodes']]} "
          f"session_summary={mw['session_summary_created']} lifetime={mw['lifetime_summary_created']}")
    print(f"  usage  : prompt={u['prompt_tokens']} completion={u['completion_tokens']} latency={u['latency_ms']}ms")
check("all 12 turns returned 200", len(CONVO) == 12 and last is not None)

# ---- endpoints
mem = requests.get(f"{BASE}/api/memory/{USER}")
print("\n### GET /api/memory\nHTTP", mem.status_code)
mem_j = mem.json()
print({k: (v if k != "episodes" and k != "messages" else f"<{len(v)} items>") for k, v in mem_j.items()})
check("memory: 200", mem.status_code == 200)
check("memory: last 16 messages returned (24 stored)", len(mem_j["messages"]) == 16)
check("memory: has session summary", mem_j["latest_session_summary"] is not None)
check("memory: has lifetime summary (scope=user)", mem_j["latest_lifetime_summary"] is not None)
check("memory: episodes returned with embeddings stored (dim 384)",
      mem_j["episodes"] and all(e["embedding_dim"] == 384 for e in mem_j["episodes"]))

agg = requests.get(f"{BASE}/api/aggregate/{USER}")
print("\n### GET /api/aggregate\nHTTP", agg.status_code, agg.json()["daily_message_counts"],
      f"| recent_summaries={len(agg.json()['recent_summaries'])}")
check("aggregate: 200 + 24 messages counted today",
      agg.status_code == 200 and sum(d["count"] for d in agg.json()["daily_message_counts"]) == 24)

# ---- failure paths
for label, payload, want in [
    ("empty message", {"user_id": USER, "message": ""}, 422),
    ("missing user_id", {"message": "hi"}, 422),
    ("bad user_id characters", {"user_id": "bad user!", "message": "hi"}, 422),
    ("unknown extra field", {"user_id": USER, "message": "hi", "foo": 1}, 422),
]:
    r = requests.post(f"{BASE}/api/chat", json=payload)
    print(f"\n### chat: {label} -> HTTP {r.status_code} {r.text[:200]}")
    check(f"chat {label} -> {want}", r.status_code == want)
r = requests.get(f"{BASE}/api/memory/no_such_user_xyz")
print("\n### memory unknown user -> HTTP", r.status_code, r.text)
check("memory unknown user -> 404", r.status_code == 404)
r = requests.put(f"{BASE}/api/settings", json={"SHORT_TERM_N": -5})
check("settings rejects SHORT_TERM_N=-5 -> 422", r.status_code == 422)

# ---- direct DB verification (bypasses the API)
n_msg = db["messages"].count_documents({"user_id": USER, "session_id": session})
n_asst = db["messages"].count_documents({"user_id": USER, "role": "assistant"})
sess = list(db["summaries"].find({"user_id": USER, "scope": "session"}))
life = list(db["summaries"].find({"user_id": USER, "scope": "user"}))
eps = list(db["episodes"].find({"user_id": USER}))
print(f"\n### Direct MongoDB: messages={n_msg} (assistant={n_asst}) session_summaries={len(sess)} "
      f"lifetime_summaries={len(life)} episodes={len(eps)}")
check("DB: 24 messages (12 user + 12 assistant)", n_msg == 24 and n_asst == 12)
check("DB: 2 session summaries (every 6 user msgs)", len(sess) == 2)
check("DB: lifetime summary has scope=user and session_id=null",
      len(life) >= 1 and all(l["session_id"] is None for l in life))
check("DB: episodes have 384-float embeddings and importance in [0,1]",
      len(eps) > 0 and all(len(e["embedding"]) == 384 and 0 <= e["importance"] <= 1 for e in eps))
print("sample episodes:", [(e["fact"], e["importance"]) for e in eps[:5]])
print("\nlifetime summary text:\n", life[-1]["text"] if life else None)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
