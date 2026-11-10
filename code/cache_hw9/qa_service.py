"""
DATA-260 Homework 9 - Part 2: the query handler at the ingress of the Q&A endpoint, with the semantic cache in front of the HW8 pipeline.

CachedQA.ask(query):
  1. embed the query                       (timed)
  2. nearest cached query in Redis         (timed)   similarity >= threshold  ->  HIT: log it, return the stored answer, is_cached=True
  3. otherwise MISS: look up the fixture facts the question depends on in MySQL, send "facts + question" through the HW8 pipeline
     (timed), and cache the answer with the query, its embedding and the data-version marker (timed) - only if the Reviewer approved it.
Every response carries is_cached, the similarity (best score seen, even on a miss) and the latency of each operation.
"""

import inspect
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kafka_hw8"))
import tracing  # noqa: E402  (HW10: structured spans, a no-op unless HW10_SPANS is set)
from facts import fingerprint, fixture_facts, lookup_facts  # noqa: E402
from semantic_cache import SemanticCache, embed, now_ms  # noqa: E402

log = logging.getLogger("qa_service")
DEFAULT_THRESHOLD = 0.85


class CachedQA:
    def __init__(self, cache: SemanticCache, agent_fn, threshold: float = DEFAULT_THRESHOLD, check_version: bool = False):
        """agent_fn(question_text) -> {status, answer, ...}; in production this is PipelineClient.ask.
        check_version (Part 3.5): on a hit, re-read the fixture rows the cached answer depends on and compare their fingerprint with
        the data-version marker stored with the entry; a mismatch means the answer is stale, so the entry is deleted and treated as a miss."""
        self.cache, self.agent_fn, self.threshold, self.check_version = cache, agent_fn, threshold, check_version
        self._agent_takes_trace = "trace_id" in inspect.signature(agent_fn).parameters  # the HW9 stand-in agents do not

    def ask(self, query: str, threshold: float | None = None, trace_id: str | None = None) -> dict:
        """trace_id (HW10): the request's one identifier. On a miss it is passed to agent_fn, which uses it as the Kafka correlation_id."""
        threshold = self.threshold if threshold is None else threshold
        trace_id = trace_id or str(uuid.uuid4())
        started_at, t0, w0 = datetime.now().isoformat(timespec="milliseconds"), now_ms(), tracing.now_ms()
        vector = embed(query)
        t1 = now_ms()
        best = self.cache.nearest(vector)
        t2 = now_ms()
        timings = {"embed_ms": t1 - t0, "search_ms": t2 - t1}
        w_lookup_end = tracing.now_ms()
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

        is_hit = bool(best and similarity >= threshold and not stale)
        tracing.emit(trace_id, "cache_lookup", w0, w_lookup_end, path="hit" if is_hit else "miss", similarity=similarity, threshold=threshold,
                     embed_ms=round(timings["embed_ms"], 1), search_ms=round(timings["search_ms"], 1), stale=stale)

        if is_hit:
            log.info("CACHE HIT  similarity=%.4f threshold=%.2f query=%r matched=%r", similarity, threshold, query, best["query"])
            result = {"answer": best["answer"], "is_cached": True, "status": best["status"], "matched_query": best["query"],
                      "data_version": best["version"]}
        else:
            log.info("CACHE MISS best_similarity=%s threshold=%.2f query=%r - running the HW8 agent pipeline",
                     "n/a (empty cache)" if similarity is None else f"{similarity:.4f}", threshold, query)
            w2 = tracing.now_ms()
            facts = lookup_facts(query)
            t3 = now_ms()
            tracing.emit(trace_id, "facts_lookup", w2, tracing.now_ms(), refs=facts["refs"])
            question_text = facts["block"] + "Question: " + query
            final = self.agent_fn(question_text, trace_id=trace_id) if self._agent_takes_trace else self.agent_fn(question_text)
            t4 = now_ms()
            w4 = tracing.now_ms()
            timings["facts_ms"], timings["agent_ms"] = t3 - t2, t4 - t3
            cached = final.get("status") == "approved"
            if cached:
                self.cache.store(query, vector, final["answer"], facts["version"], facts["refs"])
            timings["store_ms"] = now_ms() - t4
            tracing.emit(trace_id, "cache_store", w4, tracing.now_ms(), stored=cached)
            if not cached:
                log.info("not cached: pipeline status=%r", final.get("status"))
            result = {"answer": final.get("answer", ""), "is_cached": False, "status": final.get("status"), "matched_query": None,
                      "data_version": facts["version"], "stored_in_cache": cached, "invalidated_stale_entry": stale}
        total = now_ms() - t0
        failed = (not is_hit) and result["status"] in ("timeout", None)
        tracing.emit(trace_id, "request", w0, tracing.now_ms(), "error" if failed else "ok", f"pipeline status={result['status']}" if failed else None,
                     path="hit" if is_hit else "miss", pipeline_status=result["status"])
        return {"trace_id": trace_id, "query": query, **result, "similarity": similarity, "threshold": threshold, "latency_ms": round(total, 1),
                "timings_ms": {k: round(v, 1) for k, v in timings.items()}, "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="milliseconds")}
