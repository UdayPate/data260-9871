"""
DATA-260 Homework 7 - Part 1.III: schema migration for JWT roles.

The HW4 `users` table has (id, name, email, password_hash) and already holds the demo admin, so the
new columns cannot simply be declared NOT NULL - create_all() never alters an existing table. In the
only order MySQL allows for a non-empty table:

    1. ADD `username` as NULL-able and `role` ENUM('reader','writer','moderator') DEFAULT 'reader'
    2. backfill existing rows: the HW4 admin (league_admin@example.com) becomes username
       `league_admin` with role `moderator` (it was the only, all-powerful user); any other row gets
       its e-mail's local part as username and stays `reader`
    3. MODIFY `username` to NOT NULL and add the UNIQUE key

Every step is guarded by an information_schema check, so running it twice is safe. The HW4
`sessions` table is left in place (unused now; the session scheme lives on only at the hw4 tag).
The reader/writer/moderator demo users are created at server startup (auth_jwt.seed_demo_users).

Run from code/web_application, inside the venv:   python migrate_hw07.py
"""

import sys

from sqlalchemy import text

from db import MYSQL_DB, engine

LEGACY_ADMIN_EMAIL = "league_admin@example.com"


def log(msg):
    print(msg, flush=True)


def column_exists(conn, table, column):
    return conn.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = :db AND table_name = :t AND column_name = :c"),
        {"db": MYSQL_DB, "t": table, "c": column}).first() is not None


def index_exists(conn, table, index):
    return conn.execute(text(
        "SELECT 1 FROM information_schema.statistics WHERE table_schema = :db AND table_name = :t AND index_name = :i"),
        {"db": MYSQL_DB, "t": table, "i": index}).first() is not None


def is_nullable(conn, table, column):
    row = conn.execute(text(
        "SELECT is_nullable FROM information_schema.columns WHERE table_schema = :db AND table_name = :t AND column_name = :c"),
        {"db": MYSQL_DB, "t": table, "c": column}).first()
    return row is not None and row[0] == "YES"


def main():
    with engine.begin() as conn:
        log("[1/3] adding columns")
        if column_exists(conn, "users", "username"):
            log("      username: already present")
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL"))
            log("      username: added (NULL-able for now)")
        if column_exists(conn, "users", "role"):
            log("      role: already present")
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN role "
                              "ENUM('reader','writer','moderator') NOT NULL DEFAULT 'reader'"))
            log("      role: added")

        log("[2/3] backfilling existing users")
        rows = conn.execute(text("SELECT id, email FROM users WHERE username IS NULL ORDER BY id")).fetchall()
        taken = {r[0] for r in conn.execute(text("SELECT username FROM users WHERE username IS NOT NULL"))}
        for user_id, email in rows:
            if email == LEGACY_ADMIN_EMAIL:
                username, role = "league_admin", "moderator"
            else:
                username, role = email.split("@")[0][:64], "reader"
            base, n = username, 1
            while username in taken:
                n += 1
                username = f"{base}{n}"
            taken.add(username)
            conn.execute(text("UPDATE users SET username = :u, role = :r WHERE id = :i"),
                         {"u": username, "r": role, "i": user_id})
            log(f"      user {user_id} ({email}) -> username={username}, role={role}")
        if not rows:
            log("      nothing to backfill")

        log("[3/3] constraints")
        if is_nullable(conn, "users", "username"):
            conn.execute(text("ALTER TABLE users MODIFY username VARCHAR(64) NOT NULL"))
            log("      username: now NOT NULL")
        else:
            log("      username: already NOT NULL")
        if index_exists(conn, "users", "uq_users_username"):
            log("      uq_users_username: already present")
        else:
            conn.execute(text("ALTER TABLE users ADD UNIQUE KEY uq_users_username (username)"))
            log("      uq_users_username: added")

    with engine.connect() as conn:
        log("\nusers table after migration:")
        for r in conn.execute(text("SELECT id, username, email, role, LEFT(password_hash, 7) AS hash_prefix FROM users ORDER BY id")):
            log(f"      {tuple(r)}")


if __name__ == "__main__":
    sys.exit(main())
