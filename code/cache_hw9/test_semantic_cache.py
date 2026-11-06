"""
DATA-260 Homework 9 - Part 2 smoke test of the semantic cache and query handler.

REAL Redis (vector index), REAL MiniLM embeddings, REAL MySQL fixture facts. Only the agent pipeline is replaced by a fake that returns a
canned answer and counts its calls, so the test is fast and checks the cache logic itself (the real pipeline is exercised by run_part2.py).
    code\\venv\\Scripts\\python.exe code/cache_hw9/test_semantic_cache.py        (prints "N/N checks passed")
"""

import logging
import sys

from facts import fingerprint, lookup_facts
from qa_service import CachedQA
from semantic_cache import KEY_PREFIX, SemanticCache

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


class FakeAgent:
    def __init__(self):
        self.calls, self.status = [], "approved"

    def __call__(self, text):
        self.calls.append(text)
        return {"status": self.status, "answer": f"canned answer #{len(self.calls)}", "correlation_id": "fake"}


logging.getLogger("qa_service").setLevel(logging.WARNING)
cache = SemanticCache()
cache.clear()
agent = FakeAgent()
qa = CachedQA(cache, agent)
Q = "Which team is the home team for fixture FX-9871-00005?"

first = qa.ask(Q)
check("empty cache: miss, similarity None, the agent ran once, answer returned", not first["is_cached"] and first["similarity"] is None
      and len(agent.calls) == 1 and first["answer"] == "canned answer #1")
check("the miss stored one entry", cache.size() == 1)
check("the agent got the fixture facts in front of the question", "Sunnyvale Falcons" in agent.calls[0] and agent.calls[0].endswith("Question: " + Q),
      agent.calls[0].splitlines()[1][:60])

dup = qa.ask(Q)
check("exact duplicate: HIT, similarity ~1.0, the agent did not run again, stored answer returned",
      dup["is_cached"] and dup["similarity"] >= 0.999 and len(agent.calls) == 1 and dup["answer"] == "canned answer #1", f"sim={dup['similarity']}")
check("a hit reports the matched cached query", dup["matched_query"] == Q)

para = qa.ask("Tell me which team hosts fixture FX-9871-00005 at home.")
other = qa.ask("What are the basic rules of volleyball scoring?")
check("a paraphrase scores higher than an unrelated question", para["similarity"] > other["similarity"], f"paraphrase={para['similarity']} unrelated={other['similarity']}")
check("unrelated question: miss, the agent ran", not other["is_cached"] and len(agent.calls) == (3 if not para["is_cached"] else 2))

n = len(agent.calls)
strict = qa.ask(Q, threshold=1.01)
check("threshold above any possible score: even the exact duplicate misses", not strict["is_cached"] and len(agent.calls) == n + 1 and strict["similarity"] >= 0.999)
loose = qa.ask("completely different words about cooking pasta", threshold=0.0)
check("threshold 0.0: everything hits", loose["is_cached"] and loose["similarity"] is not None)

size = cache.size()
agent.status = "rejected"
rej = qa.ask("Who is the referee for the grand final tonight?")
check("a rejected pipeline answer is returned but NOT cached", not rej["is_cached"] and not rej["stored_in_cache"] and cache.size() == size and rej["status"] == "rejected")
agent.status = "timeout"
check("a pipeline timeout is not cached", not qa.ask("Another brand new question about fixtures nobody asked")["stored_in_cache"])
agent.status = "approved"

f5 = lookup_facts(Q)
entry = cache.nearest(__import__("semantic_cache").embed(Q))
check("stored data-version marker = fingerprint of the facts used; refs stored", entry["version"] == f5["version"] == fingerprint(f5["facts"])
      and entry["refs"] == ["FX-9871-00005"], f"version={entry['version']}")
check("a question without a fixture code has the 'static' marker", lookup_facts("What are the basic rules of volleyball scoring?")["version"] == "static")
ghost = lookup_facts("Who plays in fixture FX-9871-99999?")
check("unknown fixture code: facts block says it does not exist, marker differs", "no such fixture" in ghost["block"] and ghost["version"] != "static")
check("the marker changes when a fact changes", fingerprint({"A": {"spots_available": 22}}) != fingerprint({"A": {"spots_available": 21}}))

for key in ("embed_ms", "search_ms", "facts_ms", "agent_ms", "store_ms"):
    assert key in first["timings_ms"], key
check("a miss reports every operation's latency; a hit only embed+search", set(dup["timings_ms"]) == {"embed_ms", "search_ms"}
      and first["latency_ms"] >= first["timings_ms"]["agent_ms"] and dup["latency_ms"] < first["latency_ms"] + 1)
check("every cache key starts with the PREFIX", all(k.startswith("s9871:") for k in cache.r.scan_iter(f"{KEY_PREFIX}*")) and KEY_PREFIX.startswith("s9871:"))

cache.ensure_index()
cache.ensure_index()
cache.clear()
check("ensure_index is idempotent and clear() empties the cache", cache.size() == 0)

passed = sum(results)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
