"""
DATA-260 Homework 9 - Part 1 demo: 25 accesses to one fixture through increment_fixture_views().

Run from the repo root, inside the venv, with Redis (docker compose up -d redis) and MySQL running:
    code\\venv\\Scripts\\python.exe code/cache_hw9/counter_demo.py

Before the run it resets this fixture's Redis key and its `views` column to 0, so the counts start at 1. The
"Synced" line is printed only after MySQL itself (a separate query, not the method's own return value) shows the
count, so the line is evidence and not an echo. The method's own log lines go to fixture_cache_demo.log.
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text

from fixture_cache import FixtureCache

FIXTURE_ID = 5  # an existing row (ids in s9871_rel run 4..5004; rows 1-3 were deleted in earlier homework work)
sys.stdout.reconfigure(encoding="utf-8")  # the check mark below is not in the Windows console's default code page

logging.basicConfig(filename=Path(__file__).with_name("fixture_cache_demo.log"), filemode="w", encoding="utf-8", level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")
cache = FixtureCache()


def db_views() -> int:
    with cache.engine.connect() as conn:
        return conn.execute(text("SELECT views FROM fixtures WHERE id = :id"), {"id": FIXTURE_ID}).scalar_one()


cache.redis_client.delete(cache.views_key(FIXTURE_ID))
with cache.engine.begin() as conn:
    conn.execute(text("UPDATE fixtures SET views = 0 WHERE id = :id"), {"id": FIXTURE_ID})

print("=== Testing Counter ===\n")
for n in range(1, 26):
    total = cache.increment_fixture_views(FIXTURE_ID)
    print(f"Access #{n}: Total = {total}")
    if n % 10 == 0:
        print("✓ Synced views to database" if db_views() == total else "✗ NOT synced: MySQL shows a different count")

print(f"\nRedis {cache.views_key(FIXTURE_ID)} = {cache.redis_client.get(cache.views_key(FIXTURE_ID))}")
print(f"MySQL fixtures.views (fixture {FIXTURE_ID}) = {db_views()}  (last sync was at 20; views 21-25 are only in Redis until the next multiple of 10)")
