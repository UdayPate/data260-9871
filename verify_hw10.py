"""
DATA-260 Homework 10 - verify_hw10.py
A smoke test that exercises the real HW10 system and writes reports/hw10/verification.json. It does NOT modify application code and writes nothing
into reports/hw10/raw (a temp folder only; the semantic cache and the pipeline topics are reset, as in the HW9 verification).

  1. required files exist (code, results, the 20 frozen cases, the 20 human labels, the 5 screenshots)
  2. services: Kafka (the s9871 topics), Redis Stack, MySQL, Ollama with qwen3:8b
  3. Part 4.1/4.2: every span has the required fields; the miss, hit and failed traces have the right stages and errors; trace_id == the Kafka correlation_id
  4. Part 4.3: 50 requests, all confirmed misses; the stage-latency table is recomputed from the spans and matches the saved table
  5. Part 3: eval_cases.json and human_labels.csv were committed before the judge scores and are unchanged; Spearman, mean absolute difference and
     repeatability are recomputed from the per-case data and match the reported numbers
  6. Part 2: every evaluated request has the four criteria on a 1-5 scale with the difference recomputed; the evaluator's bounds hold (test_evaluator.py)
  7. REAL system: one new question through cache -> Kafka -> Planner/Writer/Reviewer (miss, then hit), spans written for the same trace_id, then
     the evaluator scores it with the local judge
  8. the dashboard renders all three pages with the right numbers (test_dashboard.py)
  9. ruff

Needs Docker (Kafka on 9092, Redis Stack on 6379), MySQL and Ollama with qwen3:8b.  Run from the repo root, inside the venv:   python verify_hw10.py
(--fast skips the check that calls the real model)
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CODE = REPO_ROOT / "code"
HW10 = REPO_ROOT / "reports" / "hw10"
RAW = HW10 / "raw"
OUTPUT = HW10 / "verification.json"
SID4, SEED, VERIFY_SEED, PORT_BASE, PREFIX = "9871", "9871", "269871", 8871, "s9871"
MODEL_CONFIG = ("judge and agents: qwen3:8b via Ollama (thinking off; judge temperature 0, seed 9871); GEval via DeepEval; embeddings "
                "sentence-transformers/all-MiniLM-L6-v2; Redis Stack 7.4; Kafka 3.9 (KRaft); facts from MySQL s9871_rel")
REQUIRED_FILES = [
    "verify_hw10.py", "docker-compose.yml", "code/kafka_hw8/tracing.py",
    *(f"code/tracing_hw10/{f}" for f in ("harness.py", "capture_traces.py", "run_latency.py", "latency_questions.py", "summarize_latency.py")),
    *(f"code/eval_hw10/{f}" for f in ("judge.py", "evaluator.py", "run_part2.py", "make_cases.py", "run_part3.py", "test_evaluator.py", "summarize_part2.py", "summarize_part3.py")),
    *(f"code/dashboard_hw10/{f}" for f in ("app.py", "data.py", "test_dashboard.py", "take_screenshots.py")),
    "reports/hw10/eval_cases.json", "reports/hw10/human_labels.csv", "reports/hw10/METRICS.md",
    *(f"reports/hw10/raw/{f}" for f in ("spans_traces.jsonl", "spans_part2.jsonl", "spans_latency.jsonl", "part4_trace_ids.json", "part2_eval_results.json",
                                        "part3_judge_scores.json", "part4_latency_requests.json", "part4_latency_table.json")),
    *(f"reports/hw10/screenshots/{f}" for f in ("fig1_summary.png", "fig2_evaluation.png", "fig3_trace_cache_miss_2505a50d.png",
                                                "fig4_trace_cache_hit_6f8c8309.png", "fig5_trace_failed_5c4340ff.png")),
]
tmp = Path(tempfile.mkdtemp(prefix="verify_hw10_"))
for d in ("kafka_hw8", "tracing_hw10", "eval_hw10", "cache_hw9", "dashboard_hw10"):
    sys.path.insert(0, str(CODE / d))


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


def jl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def pctl(values, q):
    v = sorted(values)
    k = (len(v) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


# ---------------------------------------------------------------- checks

def check_files():
    missing = [f for f in REQUIRED_FILES if not (REPO_ROOT / f).exists()]
    return not missing, f"All {len(REQUIRED_FILES)} required files present." if not missing else f"MISSING: {missing}"


def check_services():
    import redis
    from confluent_kafka.admin import AdminClient
    from facts import engine
    from sqlalchemy import text
    topics = set(AdminClient({"bootstrap.servers": "localhost:9092"}).list_topics(timeout=10).topics)
    need = {f"{PREFIX}_{t}" for t in ("inbox", "tasks", "drafts", "final")}
    r = redis.Redis(socket_timeout=3, decode_responses=True)
    mods = [m.get("name") or m.get(b"name") for m in r.module_list()]
    with engine().connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
    import urllib.request
    tags = json.loads(urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5).read())
    has_model = any(m["name"].startswith("qwen3:8b") for m in tags["models"])
    ok = need <= topics and r.ping() and any(str(m).lower() == "search" for m in mods) and n >= 5000 and has_model
    return ok, f"Kafka topics present: {sorted(need & topics)}; Redis modules incl. search: {any(str(m).lower() == 'search' for m in mods)}; MySQL fixtures={n}; qwen3:8b in Ollama: {has_model}"


def check_spans_and_traces():
    spans = [s for p in sorted(RAW.glob("spans_*.jsonl")) for s in jl(p)]
    fields = ("trace_id", "stage", "start", "end", "status", "error")
    bad = [s for s in spans if any(k not in s for k in fields) or s["status"] not in ("ok", "error") or (s["status"] == "error") != bool(s["error"])
           or s["end_ms"] < s["start_ms"]]
    ids = json.loads((RAW / "part4_trace_ids.json").read_text(encoding="utf-8"))
    by = lambda t: [s["stage"] for s in sorted((x for x in spans if x["trace_id"] == t), key=lambda x: (x["start_ms"], -x["duration_ms"]))]  # noqa: E731
    miss, hit, fail = (by(ids[k]["trace_id"]) for k in ("cache_miss_success", "cache_hit", "failed"))
    want = ["cache_lookup", "inbox", "planner", "writer", "reviewer", "final"]
    miss_ok = all(w in miss for w in want) and [m for m in miss if m in ("planner", "writer", "reviewer")] == ["planner", "writer", "reviewer"]
    hit_path = next(s["attrs"]["path"] for s in spans if s["trace_id"] == ids["cache_hit"]["trace_id"] and s["stage"] == "cache_lookup")
    miss_path = next(s["attrs"]["path"] for s in spans if s["trace_id"] == ids["cache_miss_success"]["trace_id"] and s["stage"] == "cache_lookup")
    hit_ok = hit_path == "hit" and not any(m in hit for m in ("planner", "writer", "reviewer", "inbox"))
    fspan = [s for s in spans if s["trace_id"] == ids["failed"]["trace_id"] and s["status"] == "error" and s["stage"] == "writer"]
    fail_ok = bool(fspan) and "ConnectError" in (fspan[0]["error"] or "") and ids["failed"]["failing_stage"] == "writer"
    # trace_id == the Kafka correlation_id: the saved plan/draft/final messages of every evaluated request carry the span trace_id
    ev = json.loads((RAW / "part2_eval_results.json").read_text(encoding="utf-8"))["records"]
    same = all(r["inputs"][k]["value"]["correlation_id"] == r["trace_id"] for r in ev for k in ("plan", "draft", "final"))
    return (not bad and miss_ok and hit_ok and fail_ok and miss_path == "miss" and same,
            f"{len(spans)} spans, malformed {len(bad)}; miss trace stages {miss_ok} (cache_lookup path={miss_path}); hit trace {hit_ok} (path={hit_path}, no agent spans); "
            f"failed trace -> writer error {fspan[0]['error'][:40] if fspan else None!r}; Kafka correlation_id == trace_id for {len(ev)} requests: {same}")


def check_latency():
    spans = jl(RAW / "spans_latency.jsonl")
    req = json.loads((RAW / "part4_latency_requests.json").read_text(encoding="utf-8"))
    table = json.loads((RAW / "part4_latency_table.json").read_text(encoding="utf-8"))["stages"]
    ids = [m["trace_id"] for m in req["misses"]]
    root = {s["trace_id"]: s for s in spans if s["stage"] == "request"}
    cl = {s["trace_id"]: s for s in spans if s["stage"] == "cache_lookup"}
    all_miss = len(ids) == 50 and len(set(ids)) == 50 and all(root[t]["attrs"]["path"] == "miss" and cl[t]["attrs"]["path"] == "miss" for t in ids)
    dur = lambda t, st: sum(s["duration_ms"] for s in spans if s["trace_id"] == t and s["stage"] == st)  # noqa: E731
    rows = [{"p": dur(t, "planner"), "w": dur(t, "writer"), "r": dur(t, "reviewer"), "e": dur(t, "request"),
             "q": sum(dur(t, x) for x in ("queue_inbox", "queue_tasks", "queue_drafts", "final"))} for t in ids]
    e2e = sum(r["e"] for r in rows)
    mism = []
    for key, k in (("planner", "p"), ("writer", "w"), ("reviewer", "r"), ("queue_wait_total", "q")):
        p50, p95, pct = pctl([r[k] for r in rows], 50), pctl([r[k] for r in rows], 95), 100 * sum(r[k] for r in rows) / e2e
        if abs(p50 - table[key]["p50_ms"]) > 0.15 or abs(p95 - table[key]["p95_ms"]) > 0.15 or abs(pct - table[key]["pct_of_e2e"]) > 0.15:
            mism.append(key)
    return all_miss and not mism, (f"50 distinct requests, all confirmed misses (response and cache_lookup span): {all_miss}; p50/p95/% recomputed for planner, writer, "
                                   f"reviewer, queue wait: mismatches {mism or 'none'}; stage shares of end-to-end sum to "
                                   f"{sum(table[k]['pct_of_e2e'] for k in ('cache_lookup', 'planner', 'writer', 'reviewer', 'queue_wait_total', 'facts_lookup', 'cache_store', 'other')):.1f}%")


def check_p3_stats():
    from scipy.stats import spearmanr
    cases_p, labels_p, scores_p = HW10 / "eval_cases.json", HW10 / "human_labels.csv", RAW / "part3_judge_scores.json"
    labels = {r["case_id"]: r["human_label"] for r in csv.DictReader(open(labels_p, encoding="utf-8"))}
    cases = json.loads(cases_p.read_text(encoding="utf-8"))["cases"]
    labels_ok = len(labels) == 20 and all(v.strip().isdigit() and 1 <= int(v) <= 5 for v in labels.values()) and len(cases) == 20
    sc = json.loads(scores_p.read_text(encoding="utf-8"))
    human = [labels[c["case_id"]] for c in sc["cases"]]
    human = [int(h) for h in human]
    j = [c["judge_scores"] for c in sc["cases"]]
    rho = spearmanr(human, [x[0] for x in j])[0]
    mad = sum(abs(h - x[0]) for h, x in zip(human, j, strict=True)) / 20
    pairs = [abs(x[a] - x[b]) for x in j for a, b in ((0, 1), (0, 2), (1, 2))]
    s = sc["statistics"]
    stats_ok = abs(rho - s["spearman_rho_run1"]) < 5e-4 and abs(mad - s["mean_abs_difference_run1"]) < 5e-4 and abs(sum(pairs) / 60 - s["mean_abs_change"]) < 5e-4 and max(pairs) == s["max_abs_change"]
    first = lambda path: git("log", "--diff-filter=A", "--format=%ct", "--", path).splitlines()  # noqa: E731
    t_cases, t_labels, t_scores = (int(first(f)[-1]) for f in ("reports/hw10/eval_cases.json", "reports/hw10/human_labels.csv", "reports/hw10/raw/part3_judge_scores.json"))
    add = git("log", "--diff-filter=A", "--format=%H", "--", "reports/hw10/human_labels.csv").splitlines()[-1]
    unchanged = all(git("rev-parse", f"{add}:{f}") == git("hash-object", f) for f in ("reports/hw10/eval_cases.json", "reports/hw10/human_labels.csv"))
    order = t_cases <= t_scores and t_labels <= t_scores
    return (labels_ok and stats_ok and order and unchanged,
            f"20 cases, 20 labels in 1-5: {labels_ok}; Spearman {rho:.4f}, MAD {mad:.2f}, mean/max run-to-run change {sum(pairs) / 60:.2f}/{max(pairs)} recomputed = reported: {stats_ok}; "
            f"cases+labels committed before the judge scores: {order}; unchanged since their commit: {unchanged}")


def check_p2_records():
    d = json.loads((RAW / "part2_eval_results.json").read_text(encoding="utf-8"))
    bad = []
    for r in d["records"]:
        if r["status"] != "ok":
            bad.append((r["trace_id"][:8], r["status"]))
            continue
        s = r["scores"]
        vals = [s["plan_quality"]["score"], s["writer_helpfulness"]["score"], s["final_helpfulness"]["score"]]
        fv = s["final_vs_draft"]
        ok = all(isinstance(v, int) and 1 <= v <= 5 for v in vals) and fv["difference"] == fv["final_score"] - fv["draft_score"] \
            and s["plan_quality"]["reason"] and s["writer_helpfulness"]["trace_id"] == r["trace_id"] and s["final_helpfulness"]["final_answer"] and fv["interpretation"] \
            and fv["final_equals_draft"] == (r["inputs"]["draft"]["value"]["draft"].strip() == r["inputs"]["final"]["value"]["answer"].strip())
        if not ok:
            bad.append((r["trace_id"][:8], "fields"))
    return not bad and len(d["records"]) >= 1, f"{len(d['records'])} evaluated requests; each has plan/writer/final scores 1-5 with reasons, trace_id, final answer, draft-vs-final difference and interpretation; problems: {bad or 'none'}"


def run_py(args, timeout=600):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, (r.stdout + r.stderr)


def check_evaluator_bounds():
    rc, out = run_py(["code/eval_hw10/test_evaluator.py"], 180)
    return rc == 0 and "ALL PASSED" in out, f"test_evaluator.py: {out.count('PASS ')} passed, {out.count('FAIL ')} failed (unavailable judge -> judge_unavailable promptly; missing message -> incomplete; collect stops at its deadline)"


def check_live():
    import evaluator
    import harness
    import judge as jd
    from pipeline_client import PipelineClient
    from qa_service import CachedQA
    from semantic_cache import SemanticCache, embed
    spans_file = tmp / "spans_live.jsonl"
    spans_file.write_text("", encoding="utf-8")
    cache = SemanticCache()
    cache.clear()
    procs, _ = harness.start_agents(tmp, "live", {"HW10_SPANS": str(spans_file)})
    pipeline = PipelineClient()
    try:
        pipeline.ask("Warm-up question: name one team sport.")
        embed("warm-up")
        spans_file.write_text("", encoding="utf-8")
        os.environ["HW10_SPANS"] = str(spans_file)
        qa = CachedQA(cache, pipeline.ask)
        q = "What should a league do when two teams both claim the same practice field slot?"
        t_miss, t_hit = str(uuid.uuid4()), str(uuid.uuid4())
        miss = qa.ask(q, trace_id=t_miss)
        hit = qa.ask(q, trace_id=t_hit)
        bundles, stats = evaluator.collect({t_miss}, timeout_s=60)
        rec = evaluator.evaluate(t_miss, bundles[t_miss], jd.LocalJudge())
    finally:
        pipeline.close()
        for p in procs.values():
            harness.kill(p)
    spans = jl(spans_file)
    stages = lambda t: {s["stage"] for s in spans if s["trace_id"] == t}  # noqa: E731
    miss_ok = {"cache_lookup", "inbox", "planner", "writer", "reviewer", "final", "evaluation"} <= stages(t_miss)
    hit_ok = stages(t_hit) == {"cache_lookup", "request"} and next(s for s in spans if s["trace_id"] == t_hit and s["stage"] == "cache_lookup")["attrs"]["path"] == "hit"
    scores_ok = rec["status"] == "ok" and all(1 <= rec["scores"][k]["score"] <= 5 for k in ("plan_quality", "writer_helpfulness", "final_helpfulness"))
    corr_ok = bundles[t_miss].get("final", {}).get("value", {}).get("correlation_id") == t_miss
    return (miss["is_cached"] is False and hit["is_cached"] is True and miss_ok and hit_ok and scores_ok and corr_ok,
            f"miss is_cached={miss['is_cached']} ({miss['latency_ms']:.0f} ms), repeat is_cached={hit['is_cached']} ({hit['latency_ms']:.0f} ms); miss trace has all stages + evaluation: {miss_ok}; "
            f"hit trace has only cache_lookup + request: {hit_ok}; Kafka correlation_id == trace_id: {corr_ok}; judge scores {[rec.get('scores', {}).get(k, {}).get('score') for k in ('plan_quality', 'writer_helpfulness', 'final_helpfulness')]} (status {rec['status']})")


def check_dashboard():
    rc, out = run_py(["code/dashboard_hw10/test_dashboard.py"], 300)
    return rc == 0 and "ALL PASSED" in out, f"test_dashboard.py: {out.count('PASS ')} passed, {out.count('FAIL ')} failed (Summary, Evaluation and Trace lookup pages rendered headlessly and compared with the span files)"


def check_ruff():
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "code/kafka_hw8", "code/cache_hw9", "code/tracing_hw10", "code/eval_hw10", "code/dashboard_hw10", "verify_hw10.py"],
                       capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode == 0, (r.stdout.strip().splitlines() or [""])[-1][:200]


def main():
    fast = "--fast" in sys.argv
    started = datetime.now().isoformat(timespec="seconds")
    print("verify_hw10 run at", started, flush=True)
    plan = [("required files exist", check_files),
            ("Services: Kafka topics, Redis Stack, MySQL s9871_rel, Ollama qwen3:8b", check_services),
            ("Part 4.1/4.2: span fields; miss, hit and failed traces; trace_id equals the Kafka correlation_id", check_spans_and_traces),
            ("Part 4.3: 50 confirmed cache misses; the stage-latency table is recomputed from the spans", check_latency),
            ("Part 3: cases and labels committed before the judge scores and unchanged; Spearman, MAD and repeatability recomputed", check_p3_stats),
            ("Part 2: evaluation records have four criteria on a 1-5 scale; difference and linkage recomputed", check_p2_records),
            ("Part 2: evaluator bounds (judge unavailable, missing message, collect deadline)", check_evaluator_bounds),
            ("REAL system: question -> cache miss -> Kafka agents -> evaluator; repeat -> cache hit; one trace_id throughout", check_live),
            ("Dashboard: three pages render with numbers matching the span files", check_dashboard),
            ("Ruff passes on the HW10 code", check_ruff)]
    checks = []
    for name, fn in plan:
        if fast and fn is check_live:
            continue
        print(f"... {name}", flush=True)
        r = check(name, fn)
        print(f"    [{'PASS' if r['passed'] else 'FAIL'}] {r['detail'][:400]}", flush=True)
        checks.append(r)
    passed = sum(c["passed"] for c in checks)
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if not ln.startswith("??") and "__pycache__" not in ln]
    out = {"homework": 10, "sid4": SID4, "commit_hash": git("rev-parse", "HEAD"), "tracked_files_modified_since_commit": dirty, "model_config": MODEL_CONFIG,
           "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "port_base": PORT_BASE, "run_at": started, "checks": checks, "passed": passed, "total": len(checks),
           "all_passed": passed == len(checks)}
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"\n{passed}/{len(checks)} checks passed -> {OUTPUT}")
    sys.exit(0 if out["all_passed"] else 1)


if __name__ == "__main__":
    main()
