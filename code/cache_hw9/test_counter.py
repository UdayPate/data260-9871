"""
DATA-260 Homework 9 - Part 1 tests for FixtureCache.increment_fixture_views(), against REAL Redis and REAL MySQL.

Every database assertion reads MySQL directly (a separate query), not the method's return value. Needs Redis on
localhost:6379 and the s9871_rel database. Fixtures A=5 and B=6 (existing rows; ids in s9871_rel run 4..5004) are used and their `views` restored at the end.

    code\\venv\\Scripts\\python.exe code/cache_hw9/test_counter.py        (prints "N/N checks passed")
"""

import logging
import sys

import redis
from sqlalchemy import create_engine, text

from fixture_cache import PREFIX, SYNC_EVERY, FixtureCache
from db import DATABASE_URL  # noqa: E402  (fixture_cache put web_application on sys.path)

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


capture = Capture()
logging.getLogger("fixture_cache").addHandler(capture)
logging.getLogger("fixture_cache").setLevel(logging.INFO)
cache = FixtureCache()
r = cache.redis_client
probe = create_engine(DATABASE_URL)  # a second, independent connection used only to read the truth


def db_views(fid):
    with probe.connect() as conn:
        return conn.execute(text("SELECT views FROM fixtures WHERE id = :id"), {"id": fid}).scalar()


def synced_lines():
    return [x for x in capture.records if "Synced views to database" in x.getMessage()]


A, B = 5, 6
original = {fid: db_views(fid) for fid in (A, B)}
assert None not in original.values(), "test fixtures 5 and 6 must exist in s9871_rel"
for fid in (A, B):
    r.delete(cache.views_key(fid))
    with probe.begin() as conn:
        conn.execute(text("UPDATE fixtures SET views = 0 WHERE id = :id"), {"id": fid})

try:
    # 1. the 25-access scenario from the assignment, with MySQL read after every access
    totals, db_after = [], []
    for _ in range(25):
        totals.append(cache.increment_fixture_views(A))
        db_after.append(db_views(A))
    check("returns the running total 1..25", totals == list(range(1, 26)), f"last={totals[-1]}")
    check("Redis holds the live count (GET key == 25)", r.get(cache.views_key(A)) == "25")
    check("key starts with the PREFIX", cache.views_key(A).startswith(f"{PREFIX}:"), cache.views_key(A))
    expected_db = [0] * 9 + [10] * 10 + [20] * 6
    check("MySQL changes only at 10 and 20 (read after every access)", db_after == expected_db, f"after 9={db_after[8]}, 10={db_after[9]}, 11={db_after[10]}, 20={db_after[19]}, 25={db_after[24]}")
    check("'Synced views to database' logged exactly twice (at 10 and 20)", len(synced_lines()) == 2, f"{len(synced_lines())} lines")

    # 2. counters of different fixtures are independent
    check("another fixture counts separately", [cache.increment_fixture_views(B) for _ in range(3)] == [1, 2, 3] and r.get(cache.views_key(A)) == "25")
    check("every s9871:views key starts with the PREFIX", all(k.startswith(f"{PREFIX}:views:") for k in r.scan_iter(f"{PREFIX}:views:*")))

    # 3. invalid ids are rejected before any Redis write
    keys_before = set(r.scan_iter(f"{PREFIX}:*"))
    rejected = []
    for bad in (0, -5, "1", None, True, 1.5):
        try:
            cache.increment_fixture_views(bad)
            rejected.append(False)
        except ValueError:
            rejected.append(True)
    check("0, -5, '1', None, True, 1.5 raise ValueError", all(rejected), str(rejected))
    check("rejected ids created no Redis key", set(r.scan_iter(f"{PREFIX}:*")) == keys_before)

    # 4. a fixture that is not in the database: the count works, the sync warns instead of crashing
    ghost = 9_999_999
    r.delete(cache.views_key(ghost))
    capture.records.clear()
    ghost_totals = [cache.increment_fixture_views(ghost) for _ in range(SYNC_EVERY)]
    check("unknown fixture id: counter still returns 1..10", ghost_totals == list(range(1, 11)))
    check("unknown fixture id: sync logs a warning, no 'Synced' line, no row created",
          any(x.levelno == logging.WARNING for x in capture.records) and not synced_lines() and db_views(ghost) is None)
    r.delete(cache.views_key(ghost))

    # 5. MySQL unreachable at the 10th access: the view is still counted and returned, the error is logged
    dead_db = create_engine("mysql+pymysql://nobody:none@127.0.0.1:1/s9871_rel", connect_args={"connect_timeout": 2})
    offline = FixtureCache(redis_client=r, engine=dead_db)
    r.set(cache.views_key(B), SYNC_EVERY - 1)
    capture.records.clear()
    check("MySQL down at the 10th access: returns 10 and logs an error", offline.increment_fixture_views(B) == 10
          and any(x.levelno == logging.ERROR for x in capture.records))

    # 6. Redis unreachable: nothing to count with, so the error reaches the caller
    try:
        FixtureCache(redis_client=redis.Redis(port=6390, socket_connect_timeout=1)).increment_fixture_views(A)
        check("Redis down: the error reaches the caller", False)
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as exc:  # Windows times out on a closed port
        check("Redis down: the error reaches the caller", True, type(exc).__name__)
finally:
    for fid in (A, B):
        r.delete(cache.views_key(fid))
        with probe.begin() as conn:
            conn.execute(text("UPDATE fixtures SET views = :v WHERE id = :id"), {"v": original[fid], "id": fid})

passed = sum(results)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
