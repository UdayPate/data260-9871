"""
DATA-260 Homework 9 - verify_hw09.py
A smoke test that exercises the real HW9 system and writes reports/hw09/verification.json. It does NOT modify application code;
it writes nothing into reports/hw09/raw (temp folder only). Rows it touches in s9871_rel are restored afterwards.

  1. required files exist
  2. services: Redis Stack (with the RediSearch module) and MySQL s9871_rel are up
  3. Part 1: 10 accesses -> Redis counts every one, MySQL changes only at the 10th (read directly), keys carry the s9871 prefix
  4. Part 2: semantic cache on real Redis + MiniLM + MySQL facts (the HW8 pipeline is replaced by a stub agent here):
     miss -> duplicate hit -> paraphrase hit -> unrelated miss, rejected answers not cached, hit/miss logged with similarity
  5. Part 3: the 40 labels match the database; re-running the sweep reproduces the committed hit/false-hit counts; a stale cached
     answer is served without the version check and invalidated with it (the edited row is restored)
  6. Part 4: offline agent tests; dataset files unchanged since commit (test_data.json especially); the lesson gate decisions follow
     the four rules; the results table matches the saved per-question results; REAL qwen3 turns: a forced incomplete answer is
     repaired in 2 attempts, and an off-topic question is declined with the kept lesson loaded
  7. ruff

Needs Docker (Redis Stack on 6379), MySQL, and Ollama with qwen3:8b.  Run from the repo root, inside the venv:   python verify_hw09.py
(--fast skips the checks that call the real model)
"""

import contextlib
import io
import json
import logging
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CACHE_DIR, AGENTS_DIR = REPO_ROOT / "code" / "cache_hw9", REPO_ROOT / "code" / "agents_hw9"
HW09 = REPO_ROOT / "reports" / "hw09"
VERIFICATION_OUTPUT = HW09 / "verification.json"
SID4, SEED, VERIFY_SEED, PORT_BASE, PREFIX = "9871", "9871", "269871", 8871, "s9871"
MODEL_CONFIG = ("qwen3:8b via Ollama (thinking off, temperature 0, seed 9871) for the Part 4 agents; Part 2/3 caches: sentence-transformers/"
                "all-MiniLM-L6-v2 + Redis Stack 7.4 (RediSearch FLAT, COSINE); facts from MySQL s9871_rel")
REQUIRED_FILES = [
    "verify_hw09.py", "docker-compose.yml",
    *(f"code/cache_hw9/{f}" for f in ("fixture_cache.py", "counter_demo.py", "test_counter.py", "facts.py", "semantic_cache.py", "qa_service.py",
                                      "pipeline_client.py", "run_part2.py", "cache_cases.yaml", "validate_cases.py", "sweep_part3.py",
                                      "false_hit_detail.py", "cost_model.py", "stale_demo.py", "summarize_part3.py")),
    *(f"code/agents_hw9/{f}" for f in ("agents.py", "system.py", "qa_rules.py", "make_datasets.py", "run_part4.py", "test_part4.py",
                                       "lessons.json", "lessons_candidates.json", "data/reference_dataset.json", "data/training_data.json",
                                       "data/validation_data.json", "data/test_data.json")),
    "reports/hw09/RUN_LOG.txt", "reports/hw09/METRICS.md", "reports/hw09/raw/part2_results.json", "reports/hw09/raw/part3_sweep.json",
    "reports/hw09/raw/part4_validation.json", "reports/hw09/raw/part4_test_results.json",
]
tmp = Path(tempfile.mkdtemp(prefix="verify_hw09_"))
for d in (CACHE_DIR, AGENTS_DIR):
    sys.path.insert(0, str(d))


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


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


# ---------------------------------------------------------------- checks

def check_files():
    missing = [f for f in REQUIRED_FILES if not (REPO_ROOT / f).exists()]
    return not missing, f"All {len(REQUIRED_FILES)} required files present." if not missing else f"MISSING: {missing}"


def check_services():
    import redis
    from facts import engine
    from sqlalchemy import text
    r = redis.Redis(host="localhost", port=6379, decode_responses=True, socket_timeout=3)
    pong = r.ping()
    mods = [m.get("name") or m.get(b"name") for m in r.module_list()]
    with engine().connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
    return pong and any(str(m).lower() == "search" for m in mods) and n >= 5000, f"Redis PING={pong}, modules={mods}; MySQL fixtures rows={n}"


def check_p1_counter():
    import redis
    from fixture_cache import FixtureCache
    from facts import engine
    from sqlalchemy import text
    fid, key = 6, "s9871:views:fixture:6"
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    fc = FixtureCache()

    def db_views():
        with engine().connect() as c:
            return c.execute(text("SELECT views FROM fixtures WHERE id=:i"), {"i": fid}).scalar()

    orig = db_views()
    r.delete(key)
    try:
        counts = [fc.increment_fixture_views(fid) for _ in range(9)]
        after9 = db_views()
        counts.append(fc.increment_fixture_views(fid))
        after10, live = db_views(), int(r.get(key))
    finally:
        r.delete(key)
        with engine().begin() as c:
            c.execute(text("UPDATE fixtures SET views=:v WHERE id=:i"), {"v": orig, "i": fid})
    ok = counts == list(range(1, 11)) and after9 == orig and after10 == 10 and live == 10 and key.startswith(PREFIX + ":")
    return ok, f"returned {counts[0]}..{counts[-1]}; MySQL after 9 = {after9} (was {orig}), after 10 = {after10}; Redis = {live}; views restored to {orig}"


def check_p2_cache():
    from qa_service import CachedQA
    from semantic_cache import KEY_PREFIX, SemanticCache
    cache = SemanticCache()
    cache.clear()
    calls = []
    verdict = {"status": "approved"}

    def agent(text):
        calls.append(text)
        return {**verdict, "answer": "stub answer"}

    log = io.StringIO()
    h = logging.StreamHandler(log)
    logging.getLogger("qa_service").addHandler(h)
    logging.getLogger("qa_service").setLevel(logging.INFO)
    try:
        qa = CachedQA(cache, agent, 0.85)
        q = "Which team is the home team for fixture FX-9871-00005?"
        r1, r2 = qa.ask(q), qa.ask(q)
        r3 = qa.ask("Tell me which team hosts fixture FX-9871-00005 at home.")
        r4 = qa.ask("What are the basic rules of volleyball scoring?")
        size = cache.size()
        verdict["status"] = "rejected"
        qa.ask("How many player spots are still available for fixture FX-9871-00007?")
        not_cached = cache.size() == size
        keys = list(cache.r.scan_iter(f"{KEY_PREFIX}*"))
    finally:
        logging.getLogger("qa_service").removeHandler(h)
        cache.clear()
    text = log.getvalue()
    ok = (not r1["is_cached"] and r2["is_cached"] and r2["similarity"] >= 0.999 and r3["is_cached"] and not r4["is_cached"]
          and len(calls) == 3 and not_cached and size == 2 and all(k.startswith(PREFIX + ":") for k in keys)
          and "CACHE HIT" in text and "CACHE MISS" in text and all("latency_ms" in r for r in (r1, r2, r3, r4)))
    return ok, (f"miss/dup/paraphrase/unrelated -> is_cached {[r1['is_cached'], r2['is_cached'], r3['is_cached'], r4['is_cached']]}, "
                f"paraphrase similarity {r3['similarity']}, stub agent ran {len(calls)}x, rejected answer cached: {not not_cached}")


def check_p3_labels():
    import validate_cases
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = validate_cases.main()
    return rc == 0, out.getvalue().strip().splitlines()[-1]


def check_p3_sweep():
    import sweep_part3
    committed = json.loads((HW09 / "raw" / "part3_sweep.json").read_text(encoding="utf-8"))
    mine = tmp / "sweep.json"
    argv = sys.argv
    sys.argv = ["sweep_part3.py", "--out", str(mine)]
    try:
        quiet(sweep_part3.main)
    finally:
        sys.argv = argv
    new = json.loads(mine.read_text(encoding="utf-8"))
    pairs = [(t["threshold"], t["hits"], t["false_hits"]) for t in new["thresholds"]]
    old = [(t["threshold"], t["hits"], t["false_hits"]) for t in committed["thresholds"]]
    top = new["thresholds"][-1]
    diff_hits = sum(r["hit"] for r in top["rows"] if r["category"] == "different_answer")
    return pairs == old and top["false_hits"] > 0, f"(threshold, hits, false hits) reproduced: {pairs}; different-answer cases still hit at 0.95: {diff_hits}/10"


def check_p3_stale():
    import logging as lg
    from facts import fixture_facts
    from qa_service import CachedQA
    from semantic_cache import SemanticCache
    import stale_demo as sd
    lg.getLogger("qa_service").setLevel(lg.WARNING)
    cache = SemanticCache()
    cache.clear()
    plain, versioned = CachedQA(cache, sd.agent, 0.85, False), CachedQA(cache, sd.agent, 0.85, True)
    orig = sd.db_row(sd.CODE)
    try:
        first = versioned.ask(sd.QUERY)
        sd.db_set(sd.CODE, spots_available=orig.spots_available - 5)
        truth = fixture_facts([sd.CODE])[sd.CODE]["spots_available"]
        stale = plain.ask(sd.QUERY)
        fresh = versioned.ask(sd.QUERY)
        again = versioned.ask(sd.QUERY)
    finally:
        sd.db_set(sd.CODE, spots_available=orig.spots_available)
        cache.clear()
    ok = (str(orig.spots_available) in first["answer"] and stale["is_cached"] and str(orig.spots_available) in stale["answer"]
          and str(truth) not in stale["answer"] and not fresh["is_cached"] and fresh["invalidated_stale_entry"] and str(truth) in fresh["answer"]
          and again["is_cached"] and again["answer"] == fresh["answer"])
    return ok, f"db {orig.spots_available}->{truth}; plain cache still said {stale['answer']!r}; versioned: invalidated={fresh['invalidated_stale_entry']}, new answer {fresh['answer']!r}; row restored"


def check_p4_offline():
    r = subprocess.run([sys.executable, "test_part4.py"], cwd=AGENTS_DIR, capture_output=True, text=True, encoding="utf-8", timeout=300)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    return r.returncode == 0, last


def check_p4_datasets():
    names = ["reference_dataset", "training_data", "validation_data", "test_data"]
    bad = []
    for n in names:
        rel = f"code/agents_hw9/data/{n}.json"
        if git("hash-object", rel) != git("rev-parse", f"HEAD:{rel}"):
            bad.append(n)
    files = {n: json.loads((AGENTS_DIR / "data" / f"{n}_data.json").read_text(encoding="utf-8")) for n in ("training", "validation", "test")}
    shape = all(set(i) == {"id", "question"} for d in files.values() for i in d)
    return not bad and shape, f"changed since commit: {bad or 'none'}; input files hold only id+question: {shape}; sizes {[len(d) for d in files.values()]}"


def check_p4_gate():
    va = json.loads((HW09 / "raw" / "part4_validation.json").read_text(encoding="utf-8"))
    kept_file = [ls["lesson_id"] for ls in json.loads((AGENTS_DIR / "lessons.json").read_text(encoding="utf-8"))]
    cands = [ls["lesson_id"] for ls in json.loads((AGENTS_DIR / "lessons_candidates.json").read_text(encoding="utf-8"))]
    consistent = all(d["kept"] == (not d["regressions"] and bool(d["fixed"]) and d["failures_after"] <= d["failures_before"]
                                   and d["unsupported_after"] <= d["unsupported_before"]) for d in va["decisions"])
    ok = consistent and kept_file == va["kept"] and set(kept_file) <= set(cands) and len(kept_file) < len(cands)
    return ok, f"decisions {[(d['lesson_id'], d['kept']) for d in va['decisions']]} follow the rules: {consistent}; lessons.json = {kept_file}"


def check_p4_table():
    te = json.loads((HW09 / "raw" / "part4_test_results.json").read_text(encoding="utf-8"))
    problems = []
    for k, row in te["table"].items():
        res = te["variants"][k]["results"]
        mine = (sum(r["final_result"] == "PASS" for r in res), len(res), round(sum(r["n_attempts"] for r in res) / len(res), 2))
        if mine != (row["correct"], row["questions"], row["avg_attempts"]) or any(r["n_attempts"] > 2 for r in res):
            problems.append(k)
    return not problems, f"table recomputed from the per-question results for {list(te['table'])}; mismatches {problems or 'none'}; no question used more than 2 attempts"


def check_p4_live():
    from agents import AnsweringAgent, EvaluatorAgent, LessonStore
    from system import make_variant, run_question
    ev = EvaluatorAgent()
    agent, fb = make_variant("evaluator_repair", None)
    q = "For fixture FX-9871-00005, which team is the home team and what is its home ground?"
    t = run_question(q, agent, ev, fb, forced_first_answer="The home team is Sunnyvale Falcons.")
    store = LessonStore(AGENTS_DIR / "lessons.json").copy()
    la = AnsweringAgent(store)
    t2 = run_question("What is the capital of Italy?", la, ev, use_feedback=False)
    used = t2["attempts"][0]["lessons_used"]
    ok = (t["attempts"][0]["evaluation"]["result"] == "REVISE" and t["n_attempts"] == 2 and t["final_result"] == "PASS"
          and t2["final_result"] == "PASS" and bool(used) and store.lessons[0]["use_count"] >= 1)
    return ok, (f"forced incomplete answer -> {t['attempts'][0]['evaluation']['failure_type']} -> revised -> {t['final_result']} in {t['n_attempts']} attempts; "
                f"off-topic question with lessons {used}: {t2['final_result']} ({t2['final_answer']!r})")


def check_ruff():
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "code/cache_hw9", "code/agents_hw9", "verify_hw09.py"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode == 0, (r.stdout.strip().splitlines() or [""])[-1][:200]


def main():
    fast = "--fast" in sys.argv
    started = datetime.now().isoformat(timespec="seconds")
    print("verify_hw09 run at", started, flush=True)
    plan = [("required files exist", check_files),
            ("Services: Redis Stack (RediSearch) and MySQL s9871_rel are up", check_services),
            ("Part 1: Redis counts every access, MySQL syncs only at the 10th (read directly), s9871 key prefix", check_p1_counter),
            ("Part 2: semantic cache - miss, duplicate hit, paraphrase hit, unrelated miss, rejected answer not cached, hit/miss logged", check_p2_cache),
            ("Part 3: the 40 labels in cache_cases.yaml agree with the database", check_p3_labels),
            ("Part 3: the threshold sweep reproduces the committed hit and false-hit counts", check_p3_sweep),
            ("Part 3: stale cached answer served without the version check, invalidated with it", check_p3_stale),
            ("Part 4: offline agent/evaluator/controller/lesson tests", check_p4_offline),
            ("Part 4: dataset files unchanged since commit; inputs hold only id + question", check_p4_datasets),
            ("Part 4: lesson validation decisions follow the four rules; lessons.json holds only the kept lessons", check_p4_gate),
            ("Part 4: results table matches the saved per-question results", check_p4_table),
            ("Part 4: REAL model - forced incomplete answer is repaired in 2 attempts; off-topic question declined with the kept lesson", check_p4_live),
            ("Ruff passes on the HW9 code", check_ruff)]
    checks = []
    for name, fn in plan:
        if fast and fn is check_p4_live:
            continue
        print(f"... {name}", flush=True)
        r = check(name, fn)
        print(f"    [{'PASS' if r['passed'] else 'FAIL'}] {r['detail'][:300]}", flush=True)
        checks.append(r)
    passed = sum(c["passed"] for c in checks)
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if not ln.startswith("??") and "__pycache__" not in ln]
    out = {"homework": 9, "sid4": SID4, "commit_hash": git("rev-parse", "HEAD"), "tracked_files_modified_since_commit": dirty,
           "model_config": MODEL_CONFIG, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "port_base": PORT_BASE, "run_at": started,
           "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    VERIFICATION_OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"\n{passed}/{len(checks)} checks passed -> {VERIFICATION_OUTPUT}")
    sys.exit(0 if out["all_passed"] else 1)


if __name__ == "__main__":
    main()
