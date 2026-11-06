"""
DATA-260 Homework 9 - Part 1: schema migration for the view counter.

Adds `fixtures.views INT NOT NULL DEFAULT 0` (the persisted copy of the Redis view counter). create_all() never alters an
existing table, so this ALTERs it; the information_schema check makes running it twice safe.

Run from code/web_application, inside the venv:   python migrate_hw09.py
"""

from sqlalchemy import text

from db import MYSQL_DB, engine


def main():
    with engine.begin() as conn:
        present = conn.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = :db AND table_name = 'fixtures' AND column_name = 'views'"),
            {"db": MYSQL_DB}).first() is not None
        if present:
            print("fixtures.views: already present", flush=True)
        else:
            conn.execute(text("ALTER TABLE fixtures ADD COLUMN views INT NOT NULL DEFAULT 0"))
            print("fixtures.views: added (INT NOT NULL DEFAULT 0)", flush=True)
        total, with_views = conn.execute(text("SELECT COUNT(*), SUM(views > 0) FROM fixtures")).one()
        print(f"fixtures rows: {total}, rows with views > 0: {with_views or 0}", flush=True)


if __name__ == "__main__":
    main()
