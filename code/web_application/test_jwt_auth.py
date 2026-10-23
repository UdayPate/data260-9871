"""
DATA-260 Homework 7 - Part 1: live test of JWT authentication and role-based authorization.

Real HTTP against the running server (port 8871, started from code/web_application), with MySQL checked
DIRECTLY afterwards (bypassing the API) so a response that looks right but never persisted is caught.
Everything it creates (fixtures, a team) it deletes again.

Run from code/web_application, inside the venv, with the server running:   python test_jwt_auth.py
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

logging.disable(logging.CRITICAL)            # db.py echoes every SQL statement; keep this output readable
import jwt                                    # noqa: E402
import requests                               # noqa: E402
from sqlalchemy import text                   # noqa: E402

from db import engine                         # noqa: E402  (importing db also loads .env -> JWT_SECRET)

BASE = "http://127.0.0.1:8871"
SECRET = os.environ["JWT_SECRET"]
USERS = {"reader": ("reader_user", "Reader2026!"), "writer": ("writer_user", "Writer2026!"),
         "moderator": ("moderator_user", "Moderator2026!")}
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"   ({extra})" if extra else ""))


def db_scalar(sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def login(username, password, path="/auth/login"):
    return requests.post(BASE + path, json={"username": username, "password": password}, timeout=15)


def auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


print("Run at", datetime.now().isoformat(timespec="seconds"))

# ------------------------------------------------------------------ database requirements
cols = {r[0]: r[1] for r in engine.connect().execute(text(
    "SELECT column_name, column_type FROM information_schema.columns WHERE table_schema='s9871_rel' AND table_name='users'"))}
check("users table has id, username, password_hash, role (enum reader/writer/moderator)",
      {"id", "username", "password_hash", "role"} <= set(cols) and "'reader','writer','moderator'" in cols["role"].replace(" ", ""),
      f"columns={sorted(cols)}")
check("username is UNIQUE", db_scalar("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema='s9871_rel' "
                                      "AND table_name='users' AND column_name='username' AND non_unique=0") >= 1)
hashes = [r[0] for r in engine.connect().execute(text("SELECT password_hash FROM users"))]
plain = {p for _, p in USERS.values()} | {"GoLions2026!"}
check("every stored password is a bcrypt hash, never plain text",
      hashes and all(h.startswith("$2") and len(h) == 60 and h not in plain for h in hashes), f"{len(hashes)} users")

# ------------------------------------------------------------------ login
tokens = {}
for role, (u, p) in USERS.items():
    r = login(u, p)
    ok = r.status_code == 200 and r.json().get("token_type") == "bearer" and r.json().get("access_token")
    check(f"login as {role}: valid credentials -> 200 + JWT", ok, f"HTTP {r.status_code}")
    if ok:
        tokens[role] = r.json()["access_token"]
claims = jwt.decode(tokens["writer"], options={"verify_signature": False})
hdr = jwt.get_unverified_header(tokens["writer"])
check("token is HS256 with sub/username/role/exp claims, ~30 minute lifetime",
      hdr["alg"] == "HS256" and claims["role"] == "writer" and claims["username"] == "writer_user"
      and 25 * 60 <= claims["exp"] - claims["iat"] <= 35 * 60, f"claims={ {k: claims[k] for k in ('sub', 'username', 'role')} }")

bad_pw, bad_user = login("writer_user", "wrong-password"), login("no_such_user", "whatever")
check("login with a wrong password -> 401", bad_pw.status_code == 401, bad_pw.text[:70])
check("login with an unknown username -> 401, same message (no user enumeration)",
      bad_user.status_code == 401 and bad_user.json() == bad_pw.json())
check("login with a 200-byte password does not crash (401)", login("writer_user", "x" * 200).status_code in (401, 422))
check("login missing a field -> 422", requests.post(BASE + "/auth/login", json={"username": "writer_user"}).status_code == 422)
check("old HW4 email-based login body is rejected (422)",
      requests.post(BASE + "/auth/login", json={"email": "league_admin@example.com", "password": "GoLions2026!"}).status_code == 422)
check("the same login also works under /api/auth/login (React client path)",
      login("writer_user", "Writer2026!", "/api/auth/login").status_code == 200
      and login("writer_user", "nope", "/api/auth/login").status_code == 401)

# ------------------------------------------------------------------ /auth/me and bad tokens
me = requests.get(BASE + "/auth/me", headers=auth(tokens["moderator"]))
check("GET /auth/me with a valid token -> 200 with identity and role",
      me.status_code == 200 and me.json()["role"] == "moderator" and me.json()["username"] == "moderator_user", me.text[:90])
no_tok = requests.get(BASE + "/auth/me")
check("GET /auth/me without a token -> 401 (+ WWW-Authenticate: Bearer)",
      no_tok.status_code == 401 and no_tok.headers.get("www-authenticate") == "Bearer", no_tok.text)
now = datetime.now(timezone.utc)
uid = claims["sub"]
mk = lambda **kw: jwt.encode({"sub": uid, "iat": now, "exp": now + timedelta(minutes=5), **kw.pop("claims", {})},
                             kw.pop("secret", SECRET), algorithm=kw.pop("alg", "HS256"))
cases = {
    "garbage string": "not-a-jwt",
    "tampered signature": tokens["writer"][:-4] + ("AAAA" if not tokens["writer"].endswith("AAAA") else "BBBB"),
    "signed with another secret": mk(secret="some-other-secret-that-is-long-enough-1234567890"),
    "unsigned alg=none token": jwt.encode({"sub": uid, "exp": now + timedelta(minutes=5)}, key=None, algorithm="none"),
    "token for a user id that does not exist": mk(claims={"sub": "999999"}),
    "token with no exp claim": jwt.encode({"sub": uid}, SECRET, algorithm="HS256"),
}
for label, tok in cases.items():
    r = requests.get(BASE + "/auth/me", headers=auth(tok))
    check(f"GET /auth/me with {label} -> 401", r.status_code == 401, r.text[:60])
expired = mk(claims={"exp": now - timedelta(minutes=1), "iat": now - timedelta(minutes=31)})
r = requests.get(BASE + "/auth/me", headers=auth(expired))
check("GET /auth/me with an EXPIRED token -> 401 'Token expired'", r.status_code == 401 and "expired" in r.text.lower(), r.text)
r = requests.get(BASE + "/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
check("a non-Bearer Authorization header -> 401", r.status_code == 401)
r = requests.get(BASE + "/auth/me", cookies={"session_token": "0123456789abcdef"})
check("the old HW4 session cookie no longer authenticates -> 401", r.status_code == 401)

# ------------------------------------------------------------------ role matrix on the domain routes
team_id = requests.get(BASE + "/api/teams", headers=auth(tokens["reader"])).json()["items"][0]["id"]
suffix = int(time.time()) % 1000                  # makes the test codes unique per run


def fx(n):
    return {"fixture_name": f"JWT test fixture {n}", "teams_players": "A vs B",
            "fixture_code": f"FX-9871-9{suffix:03d}{n}", "spots_available": 10, "home_team_id": team_id}


first_id = requests.get(BASE + "/api/fixtures", headers=auth(tokens["reader"])).json()[0]["id"]   # fixtures: plain list
for role in ("none", "reader", "writer", "moderator"):
    tok = tokens.get(role)
    lst = requests.get(BASE + "/api/fixtures", headers=auth(tok)).status_code
    one = requests.get(BASE + f"/api/fixtures/{first_id}", headers=auth(tok)).status_code
    want = 401 if role == "none" else 200
    check(f"list + read fixtures as {role} -> {want}", lst == want and one == want, f"list={lst} read={one}")

created = {}
for i, (role, want) in enumerate([("none", 401), ("reader", 403), ("writer", 201), ("moderator", 201)]):
    r = requests.post(BASE + "/api/fixtures", json=fx(i), headers=auth(tokens.get(role)))
    check(f"create fixture as {role} -> {want}", r.status_code == want, f"HTTP {r.status_code} {r.text[:60] if r.status_code != 201 else ''}")
    if r.status_code == 201:
        created[role] = r.json()["id"]
n_rows = db_scalar("SELECT COUNT(*) FROM fixtures WHERE fixture_name LIKE 'JWT test fixture %'")
check("only the 2 permitted creates reached MySQL (reader/none were blocked before the database)", n_rows == 2, f"{n_rows} rows")

fid = created["writer"]
cur = requests.get(BASE + f"/api/fixtures/{fid}", headers=auth(tokens["writer"])).json()
body = {k: cur[k] for k in ("fixture_name", "teams_players", "fixture_code", "spots_available", "home_team_id")}
r = requests.put(BASE + f"/api/fixtures/{fid}", json={**body, "spots_available": 1}, headers=auth(tokens["reader"]))
check("update fixture as reader -> 403 and the row is unchanged",
      r.status_code == 403 and db_scalar("SELECT spots_available FROM fixtures WHERE id=:i", i=fid) == 10, r.text[:70])
r = requests.put(BASE + f"/api/fixtures/{fid}", json={**body, "spots_available": 3}, headers=auth(tokens["writer"]))
check("update fixture as writer -> 200 and persisted in MySQL",
      r.status_code == 200 and db_scalar("SELECT spots_available FROM fixtures WHERE id=:i", i=fid) == 3, f"HTTP {r.status_code}")

mid = created["moderator"]
cur_m = requests.get(BASE + f"/api/fixtures/{mid}", headers=auth(tokens["moderator"])).json()
body_m = {k: cur_m[k] for k in ("fixture_name", "teams_players", "fixture_code", "spots_available", "home_team_id")}
r = requests.put(BASE + f"/api/fixtures/{mid}", json={**body_m, "spots_available": 4}, headers=auth(tokens["moderator"]))
check("update fixture as moderator -> 200 and persisted in MySQL",
      r.status_code == 200 and db_scalar("SELECT spots_available FROM fixtures WHERE id=:i", i=mid) == 4, f"HTTP {r.status_code}")

for role, want in [("none", 401), ("reader", 403), ("writer", 403)]:
    r = requests.delete(BASE + f"/api/fixtures/{fid}", headers=auth(tokens.get(role)))
    check(f"delete fixture as {role} -> {want}", r.status_code == want, f"HTTP {r.status_code}")
check("the blocked deletes left the row in MySQL", db_scalar("SELECT COUNT(*) FROM fixtures WHERE id=:i", i=fid) == 1)
r = requests.delete(BASE + f"/api/fixtures/{fid}", headers=auth(tokens["moderator"]))
check("delete fixture as moderator -> 200/204 and the row is really gone from MySQL",
      r.status_code in (200, 204) and db_scalar("SELECT COUNT(*) FROM fixtures WHERE id=:i", i=fid) == 0, f"HTTP {r.status_code}")
r = requests.delete(BASE + f"/api/fixtures/{created['moderator']}", headers=auth(tokens["moderator"]))
check("cleanup: moderator deletes the second test fixture", r.status_code in (200, 204))
check("delete of a nonexistent fixture as moderator -> 404 (authorized, but not found)",
      requests.delete(BASE + "/api/fixtures/99999999", headers=auth(tokens["moderator"])).status_code == 404)

# teams use the same rules
tcode = f"TM-9{suffix:03d}"
tbody = {"team_name": "JWT Test Team", "home_ground": "Test Ground", "team_code": tcode}
check("create team as reader -> 403", requests.post(BASE + "/api/teams", json=tbody, headers=auth(tokens["reader"])).status_code == 403)
r = requests.post(BASE + "/api/teams", json=tbody, headers=auth(tokens["writer"]))
check("create team as writer -> 201", r.status_code == 201, f"HTTP {r.status_code}")
tid = r.json().get("id")
check("delete team as writer -> 403", requests.delete(BASE + f"/api/teams/{tid}", headers=auth(tokens["writer"])).status_code == 403)
check("delete team as moderator -> 204/200",
      requests.delete(BASE + f"/api/teams/{tid}", headers=auth(tokens["moderator"])).status_code in (200, 204)
      and db_scalar("SELECT COUNT(*) FROM teams WHERE team_code=:c", c=tcode) == 0)

# the role is read from MySQL on every request, not trusted from the token
with engine.begin() as c:
    c.execute(text("UPDATE users SET role='reader' WHERE username='writer_user'"))
try:
    r = requests.post(BASE + "/api/fixtures", json=fx(9), headers=auth(tokens["writer"]))
    check("demoting a user in MySQL takes effect on their EXISTING token (writer token -> 403)", r.status_code == 403, f"HTTP {r.status_code}")
finally:
    with engine.begin() as c:
        c.execute(text("UPDATE users SET role='writer' WHERE username='writer_user'"))
r = requests.post(BASE + "/api/fixtures", json=fx(8), headers=auth(tokens["writer"]))
check("role restored in MySQL; the same writer token can create again (201)", r.status_code == 201, f"HTTP {r.status_code}")
if r.status_code == 201:
    requests.delete(BASE + f"/api/fixtures/{r.json()['id']}", headers=auth(tokens["moderator"]))

leftover = db_scalar("SELECT COUNT(*) FROM fixtures WHERE fixture_name LIKE 'JWT test fixture%'")
check("no test data left behind", leftover == 0, f"{leftover} leftover rows")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
for n in failed:
    print("FAILED:", n)
sys.exit(1 if failed else 0)
