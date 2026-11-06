"""
DATA-260 Homework 9 - Part 1: Redis-backed view counter for the primary entity (Fixture, domain 7).

increment_fixture_views(fixture_id) INCRs a Redis key on every access and, every SYNC_EVERY (10) views, copies the
current count into the `fixtures.views` column of s9871_rel (added by web_application/migrate_hw09.py) and logs
"Synced views to database". It returns the current count.

Reuses the HW4/HW5 MySQL setup: the connection URL and credentials come from web_application/db.py (same .env). It
builds its own engine because db.py's engine has echo=True, which would print every SQL statement of every access.
"""

import logging
import sys
from pathlib import Path

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web_application"))
from db import DATABASE_URL  # noqa: E402

PREFIX = "s9871"
SYNC_EVERY = 10
log = logging.getLogger("fixture_cache")


class FixtureCache:
    def __init__(self, redis_client=None, engine=None):
        self.redis_client = redis_client or redis.Redis(host="localhost", port=6379, decode_responses=True)
        self.engine = engine or create_engine(DATABASE_URL)

    @staticmethod
    def views_key(fixture_id: int) -> str:
        return f"{PREFIX}:views:fixture:{fixture_id}"

    def increment_fixture_views(self, fixture_id: int) -> int:
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id < 1:
            raise ValueError(f"fixture_id must be a positive integer, got {fixture_id!r}")
        count = self.redis_client.incr(self.views_key(fixture_id))  # atomic, so concurrent accesses never lose a view
        if count % SYNC_EVERY == 0:
            try:
                with self.engine.begin() as conn:
                    result = conn.execute(text("UPDATE fixtures SET views = :views WHERE id = :id"),
                                          {"views": count, "id": fixture_id})
                if result.rowcount:
                    log.info("Synced views to database")
                else:
                    log.warning("Sync skipped: no fixture with id %s in the database (count kept in Redis)", fixture_id)
            except SQLAlchemyError as exc:  # counting a view must not fail because MySQL is down; the next sync catches up
                log.error("Sync to database failed for fixture %s at count %s: %s", fixture_id, count, type(exc).__name__)
        return count
