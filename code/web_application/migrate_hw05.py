"""
DATA-260 Homework 5 - Part 1.I: schema migration.

The HW4 database (s9871_rel) already holds ~5,000 `fixtures` rows, so the
new columns cannot simply be declared NOT NULL - SQLAlchemy's
create_all() never alters an existing table. This script performs the
real migration, in the only order MySQL allows for a non-empty table:

    1. create `teams` (the HW5 related entity) and seed 12 real teams
    2. ADD the new `fixtures` columns as NULL-able
    3. backfill every existing row deterministically (SEED = 9871)
    4. MODIFY the columns to NOT NULL, then add the UNIQUE key and the
       ON DELETE RESTRICT foreign key

Every step is guarded by an information_schema check, so the script is
idempotent: running it twice is safe and the second run reports
"already present" instead of failing.

Run from code/web_application, inside the venv:
    python migrate_hw05.py
"""

import sys

from sqlalchemy import text

from db import Base, engine, db_session_basede26, MYSQL_DB
import models
from models import Fixture, Team

SEED = 9871
FIXTURE_CODE_TEMPLATE = "FX-9871-%05d"

# 12 teams, matching the team names and cities HW4's seed_n1_data.py used
# so the backfilled fixtures stay consistent with their existing
# free-text `teams_players` values.
TEAMS = [
    ("Milpitas Lions", "Milpitas Sports Complex, Field 1"),
    ("San Jose Tigers", "Watson Park, San Jose"),
    ("Fremont Warriors", "Central Park Fields, Fremont"),
    ("Santa Clara Strikers", "Central Park Softball Field, Santa Clara"),
    ("Sunnyvale Falcons", "Fair Oaks Park, Sunnyvale"),
    ("Oakland Titans", "Mosswood Park, Oakland"),
    ("Milpitas Eagles", "Cardoza Park, Milpitas"),
    ("San Jose Sharks", "Backesto Park, San Jose"),
    ("Fremont Wolves", "Northgate Park, Fremont"),
    ("Santa Clara Bears", "Westwood Oaks Park, Santa Clara"),
    ("Sunnyvale Hawks", "Ortega Park, Sunnyvale"),
    ("Oakland Panthers", "Bushrod Park, Oakland"),
]


def log(msg):
    print(msg, flush=True)


def column_exists(conn, table, column):
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :db AND table_name = :t AND column_name = :c"
        ),
        {"db": MYSQL_DB, "t": table, "c": column},
    ).first()
    return row is not None


def index_exists(conn, table, index):
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.statistics "
            "WHERE table_schema = :db AND table_name = :t AND index_name = :i"
        ),
        {"db": MYSQL_DB, "t": table, "i": index},
    ).first()
    return row is not None


def constraint_exists(conn, table, name):
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :db AND table_name = :t AND constraint_name = :n"
        ),
        {"db": MYSQL_DB, "t": table, "n": name},
    ).first()
    return row is not None


def is_nullable(conn, table, column):
    row = conn.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = :db AND table_name = :t AND column_name = :c"
        ),
        {"db": MYSQL_DB, "t": table, "c": column},
    ).first()
    return row is not None and row[0] == "YES"


def run_ddl(conn, sql):
    log(f"  [DDL] {sql}")
    conn.execute(text(sql))


# ---------------------------------------------------------------------
# Step 1 - teams table + seed rows
# ---------------------------------------------------------------------

def step1_teams():
    log("\n=== Step 1: create and seed `teams` ===")
    Base.metadata.create_all(bind=engine, tables=[Team.__table__])
    log("  teams table present (created if it was missing)")

    db = db_session_basede26()
    try:
        existing = db.query(Team).count()
        if existing:
            log(f"  teams already holds {existing} rows - not re-seeding")
            return
        for i, (name, ground) in enumerate(TEAMS, start=1):
            db.add(Team(team_name=name, home_ground=ground, team_code="TM-%04d" % i))
        db.commit()
        log(f"  seeded {db.query(Team).count()} teams "
            f"(TM-0001 .. TM-{len(TEAMS):04d})")
    finally:
        db.close()


# ---------------------------------------------------------------------
# Step 2 - add the new fixtures columns as NULL-able
# ---------------------------------------------------------------------

NEW_COLUMNS = [
    ("fixture_code", "ALTER TABLE fixtures ADD COLUMN fixture_code VARCHAR(24) NULL"),
    ("spots_available",
     "ALTER TABLE fixtures ADD COLUMN spots_available INT NOT NULL DEFAULT 22"),
    ("home_team_id", "ALTER TABLE fixtures ADD COLUMN home_team_id INT NULL"),
    ("created_at",
     "ALTER TABLE fixtures ADD COLUMN created_at DATETIME NOT NULL "
     "DEFAULT CURRENT_TIMESTAMP"),
    ("updated_at",
     "ALTER TABLE fixtures ADD COLUMN updated_at DATETIME NOT NULL "
     "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
]


def step2_add_columns(conn):
    log("\n=== Step 2: add new `fixtures` columns ===")
    for column, ddl in NEW_COLUMNS:
        if column_exists(conn, "fixtures", column):
            log(f"  fixtures.{column} already present - skipping")
        else:
            run_ddl(conn, ddl)


# ---------------------------------------------------------------------
# Step 3 - backfill existing rows
# ---------------------------------------------------------------------

def step3_backfill(conn):
    log("\n=== Step 3: backfill existing rows ===")
    total = conn.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
    log(f"  fixtures rows to consider: {total}")

    # fixture_code is derived from the primary key, so it is unique by
    # construction and identical on every re-run.
    missing_code = conn.execute(
        text("SELECT COUNT(*) FROM fixtures WHERE fixture_code IS NULL")
    ).scalar()
    if missing_code:
        conn.execute(
            text(
                "UPDATE fixtures SET fixture_code = CONCAT('FX-9871-', LPAD(id, 5, '0')) "
                "WHERE fixture_code IS NULL"
            )
        )
        log(f"  backfilled fixture_code on {missing_code} rows "
            f"(pattern {FIXTURE_CODE_TEMPLATE % 1})")
    else:
        log("  fixture_code: nothing to backfill")

    team_ids = [r[0] for r in conn.execute(text("SELECT id FROM teams ORDER BY id")).all()]
    if not team_ids:
        sys.exit("ABORT: teams table is empty - cannot backfill home_team_id")

    missing_team = conn.execute(
        text("SELECT COUNT(*) FROM fixtures WHERE home_team_id IS NULL")
    ).scalar()
    if missing_team:
        # Deterministic round-robin over the seeded team ids, keyed on the
        # fixture's own primary key - same result on every re-run, no RNG.
        lo, n = team_ids[0], len(team_ids)
        conn.execute(
            text(
                "UPDATE fixtures SET home_team_id = :lo + MOD(id - 1, :n) "
                "WHERE home_team_id IS NULL"
            ),
            {"lo": lo, "n": n},
        )
        log(f"  backfilled home_team_id on {missing_team} rows "
            f"(round-robin over team ids {lo}..{lo + n - 1})")
    else:
        log("  home_team_id: nothing to backfill")


# ---------------------------------------------------------------------
# Step 4 - tighten constraints
# ---------------------------------------------------------------------

def step4_constraints(conn):
    log("\n=== Step 4: NOT NULL + UNIQUE + ON DELETE RESTRICT foreign key ===")

    if is_nullable(conn, "fixtures", "fixture_code"):
        run_ddl(conn, "ALTER TABLE fixtures MODIFY fixture_code VARCHAR(24) NOT NULL")
    else:
        log("  fixtures.fixture_code already NOT NULL")

    if is_nullable(conn, "fixtures", "home_team_id"):
        run_ddl(conn, "ALTER TABLE fixtures MODIFY home_team_id INT NOT NULL")
    else:
        log("  fixtures.home_team_id already NOT NULL")

    if index_exists(conn, "fixtures", "uq_fixtures_fixture_code"):
        log("  UNIQUE key uq_fixtures_fixture_code already present")
    else:
        run_ddl(
            conn,
            "ALTER TABLE fixtures ADD CONSTRAINT uq_fixtures_fixture_code "
            "UNIQUE (fixture_code)",
        )

    if constraint_exists(conn, "fixtures", "fk_fixtures_home_team"):
        log("  foreign key fk_fixtures_home_team already present")
    else:
        run_ddl(
            conn,
            "ALTER TABLE fixtures ADD CONSTRAINT fk_fixtures_home_team "
            "FOREIGN KEY (home_team_id) REFERENCES teams (id) ON DELETE RESTRICT",
        )


def main():
    log("DATA-260 HW5 Part 1.I migration")
    log(f"database = {MYSQL_DB}   SEED = {SEED}")

    step1_teams()
    with engine.begin() as conn:
        step2_add_columns(conn)
        step3_backfill(conn)
        step4_constraints(conn)

    log("\n=== Final schema ===")
    with engine.connect() as conn:
        for table in ("teams", "fixtures"):
            ddl = conn.execute(text(f"SHOW CREATE TABLE {table}")).first()[1]
            log(f"\n{ddl};")
        for table in ("teams", "fixtures"):
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            log(f"\nrow count {table} = {count}")
    log("\nMigration complete.")


if __name__ == "__main__":
    main()
