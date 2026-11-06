"""
DATA-260 Homework 9 - Part 2: the query handler at the ingress of the Q&A endpoint, with the semantic cache in front of the HW8 pipeline.

CachedQA.ask(query):
  1. embed the query                       (timed)
  2. nearest cached query in Redis         (timed)   similarity >= threshold  ->  HIT: log it, return the stored answer, is_cached=True
  3. otherwise MISS: look up the fixture facts the question depends on in MySQL, send "facts + question" through the HW8 pipeline
     (timed), and cache the answer with the query, its embedding and the data-version marker (timed) - only if the Reviewer approved it.
Every response carries is_cached, the similarity (best score seen, even on a miss) and the latency of each operation.
"""

import logging
from datetime import datetime

from facts import fingerprint, fixture_facts, lookup_facts
from semantic_cache import SemanticCache, embed, now_ms

log = logging.getLogger("qa_service")
DEFAULT_THRESHOLD = 0.85


class CachedQA:
    def __init__(self, cache: SemanticCache, agent_fn, threshold: float = DEFAULT_THRESHOLD, check_version: bool = False):
        """agent_fn(question_text) -> {status, answer, ...}; in production this is PipelineClient.ask.
        check_version (Part 3.5): on a hit, re-read the fixture rows the cached answer depends on and compare their fingerprint with
        the data-version marker stored with the entry; a mismatch means the answer is stale, so the entry is deleted and treated as a miss."""
        self.cache, self.agent_fn, self.threshold, self.check_version = cache, agent_fn, threshold, check_version

    def ask(self, query: str, threshold: float | None = None) -> dict:
        threshold = self.threshold if threshold is None else threshold
        started_at, t0 = datetime.now().isoformat(timespec="milliseconds"), now_ms()
        vector = embed(query)
        t1 = now_ms()
        best = self.cache.nearest(vector)
        t2 = now_ms()
        timings = {"embed_ms": t1 - t0, "search_ms": t2 - t1}
        similarity = best["similarity"] if best else None

        stale = False
        if best and similarity >= threshold and self.check_version and best["refs"]:
            t_v = now_ms()
            current = fingerprint(fixture_facts(best["refs"]))
            timings["version_check_ms"] = now_ms() - t_v
            if current != best["version"]:
                stale = True
                self.cache.delete(best["key"])
                log.warning("CACHE STALE similarity=%.4f stored_version=%s current_version=%s refs=%s - entry %r invalidated",
                            similarity, best["version"], current, best["refs"], best["query"])

        if best and similarity >= threshold and not stale:
            log.info("CACHE HIT  similarity=%.4f threshold=%.2f query=%r matched=%r", similarity, threshold, query, best["query"])
            result = {"answer": best["answer"], "is_cached": True, "status": best["status"], "matched_query": best["query"],
                      "data_version": best["version"]}
        else:
            log.info("CACHE MISS best_similarity=%s threshold=%.2f query=%r - running the HW8 agent pipeline",
                     "n/a (empty cache)" if similarity is None else f"{similarity:.4f}", threshold, query)
            facts = lookup_facts(query)
            t3 = now_ms()
            final = self.agent_fn(facts["block"] + "Question: " + query)
            t4 = now_ms()
            timings["facts_ms"], timings["agent_ms"] = t3 - t2, t4 - t3
            cached = final.get("status") == "approved"
            if cached:
                self.cache.store(query, vector, final["answer"], facts["version"], facts["refs"])
            timings["store_ms"] = now_ms() - t4
            if not cached:
                log.info("not cached: pipeline status=%r", final.get("status"))
            result = {"answer": final.get("answer", ""), "is_cached": False, "status": final.get("status"), "matched_query": None,
                      "data_version": facts["version"], "stored_in_cache": cached, "invalidated_stale_entry": stale}
        total = now_ms() - t0
        return {"query": query, **result, "similarity": similarity, "threshold": threshold, "latency_ms": round(total, 1),
                "timings_ms": {k: round(v, 1) for k, v in timings.items()}, "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="milliseconds")}
