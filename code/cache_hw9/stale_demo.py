"""
DATA-260 Homework 9 - Part 3.5: a stale cached answer, and invalidation with the stored data-version marker.

Cached query: "How many player spots are available for fixture FX-9871-00013?" - its answer depends on fixtures.spots_available of ONE
s9871_rel row. Steps (each is a PASS/FAIL check against the database read directly, bypassing the cache):
  1 miss -> answer cached with version marker v1      2 repeat -> hit
  3 controls: a Part 1 view-counter sync on that row, and an edit to a DIFFERENT fixture, must NOT invalidate (hits still)
  4 UPDATE spots_available 22 -> 17 on the row         5 plain cache (check_version=False): STALE HIT, old answer "22"
  6 versioned cache (check_version=True): mismatch detected, entry deleted, pipeline re-run, new answer "17" cached
  7 repeat -> hit with the fresh answer, exactly one entry     8 cost of the check: mean hit latency without / with it
The agent is a stand-in that answers from the facts block it is given (the real Planner/Writer/Reviewer path was exercised in Part 2);
what is under test here is the cache's staleness handling. The edited rows are restored at the end.
"""

import json
import logging
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))
from facts import FIXTURE_CODE, engine, fixture_facts  # noqa: E402
from qa_service import CachedQA  # noqa: E402
from semantic_cache import SemanticCache  # noqa: E402
from validate_cases import answer_from_facts  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "reports" / "hw09" / "raw"
CODE, OTHER = "FX-9871-00013", "FX-9871-00014"
QUERY = f"How many player spots are available for fixture {CODE}?"
THRESHOLD = 0.85


def db_row(code):
    with engine().connect() as c:
        return c.execute(text("SELECT spots_available, views, updated_at FROM fixtures WHERE fixture_code=:c"), {"c": code}).one()


def db_set(code, **cols):
    sets = ", ".join(f"{k}=:{k}" for k in cols)
    with engine().begin() as c:
        n = c.execute(text(f"UPDATE fixtures SET {sets} WHERE fixture_code=:c"), {**cols, "c": code}).rowcount
    assert n == 1, f"{code}: {n} rows updated"


def agent(question_text):
    """Stand-in agent: reads the fixture code in the question and answers 'spots' from the facts it was given."""
    code = FIXTURE_CODE.findall(question_text)[0].upper()
    spots = int(re.search(rf"{code}.*?player spots available: (\d+)", question_text).group(1))
    return {"status": "approved", "answer": answer_from_facts({"spots_available": spots}, "spots")}


def main() -> int:
    log_path = RAW / "part3_stale.log"
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.getLogger("qa_service").addHandler(handler)
    logging.getLogger("qa_service").setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    logging.getLogger("qa_service").addHandler(console)

    cache = SemanticCache()
    cache.clear()
    plain = CachedQA(cache, agent, THRESHOLD, check_version=False)
    versioned = CachedQA(cache, agent, THRESHOLD, check_version=True)
    orig, orig_other = db_row(CODE), db_row(OTHER)
    checks, steps = [], {}

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        print(f'[{"PASS" if ok else "FAIL"}] {name}  {detail}')

    try:
        r = versioned.ask(QUERY)
        steps["1_miss"] = r
        check("1. first ask is a miss and the answer is cached", not r["is_cached"] and r["stored_in_cache"] and cache.size() == 1, r["answer"])
        v1 = r["data_version"]
        r = versioned.ask(QUERY)
        steps["2_hit"] = r
        check("2. repeat is a hit with the same answer", r["is_cached"] and r["data_version"] == v1, f'similarity={r["similarity"]}')

        db_set(CODE, views=orig.views + 1)
        after_views = db_row(CODE)
        r = versioned.ask(QUERY)
        steps["3a_views_sync"] = r
        check("3a. control: a view-counter sync (updated_at changes) does NOT invalidate",
              after_views.updated_at != orig.updated_at and r["is_cached"],
              f"updated_at {orig.updated_at} -> {after_views.updated_at}, still a hit")
        db_set(OTHER, spots_available=orig_other.spots_available - 2)
        r = versioned.ask(QUERY)
        steps["3b_other_fixture"] = r
        check("3b. control: editing a different fixture does NOT invalidate", r["is_cached"])
        db_set(OTHER, spots_available=orig_other.spots_available)

        new_spots = orig.spots_available - 5
        db_set(CODE, spots_available=new_spots)
        truth = answer_from_facts({"spots_available": db_row(CODE).spots_available}, "spots")
        check("4. database now says the new value (read directly)", truth == answer_from_facts({"spots_available": new_spots}, "spots"), truth)

        r = plain.ask(QUERY)
        steps["5_stale_hit"] = r
        check("5. STALE HIT without a version check: cache still returns the old answer", r["is_cached"] and r["answer"] != truth,
              f'cache says {r["answer"]!r}; database says {truth!r}')

        r = versioned.ask(QUERY)
        steps["6_invalidated"] = r
        check("6. with the version check: stale entry detected, pipeline re-run, fresh answer", not r["is_cached"] and r["invalidated_stale_entry"]
              and r["answer"] == truth and r["data_version"] != v1, f'new answer {r["answer"]!r}, version {v1} -> {r["data_version"]}')
        r = versioned.ask(QUERY)
        steps["7_fresh_hit"] = r
        check("7. repeat is a hit with the fresh answer; exactly one entry (stale one deleted)",
              r["is_cached"] and r["answer"] == truth and cache.size() == 1, f"entries={cache.size()}")

        logging.getLogger("qa_service").removeHandler(console)  # the 60 timing hits go to the log file only
        lat = {}
        for name, svc in (("without_check", plain), ("with_check", versioned)):
            lat[name] = [svc.ask(QUERY)["latency_ms"] for _ in range(30)]
        steps["8_hit_latency_ms"] = {k: {"mean": round(statistics.mean(v), 2), "n": len(v)} for k, v in lat.items()}
        check("8. cost of the check measured (30 hits each)", True,
              f'mean hit latency {steps["8_hit_latency_ms"]["without_check"]["mean"]} ms without, {steps["8_hit_latency_ms"]["with_check"]["mean"]} ms with')
    finally:
        db_set(CODE, spots_available=orig.spots_available, views=orig.views)
        db_set(OTHER, spots_available=orig_other.spots_available)
        cache.clear()
        back = fixture_facts([CODE])[CODE]["spots_available"]
        print(f"restored: {CODE} spots_available={back}, views={db_row(CODE).views}; cache cleared")

    out = {"part": "3.5", "run_at": datetime.now().isoformat(timespec="seconds"), "query": QUERY, "fixture": CODE, "threshold": THRESHOLD,
           "old_spots": orig.spots_available, "new_spots": new_spots, "checks": checks, "steps": steps,
           "restored_spots": back}
    (RAW / "part3_stale_results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    ok = all(c["pass"] for c in checks)
    print(f"\n{sum(c['pass'] for c in checks)}/{len(checks)} checks passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
