"""
DATA-260 Homework 4 - verify_hw04.py
A self-check smoke test confirming the HW4 system works. Writes its results to
reports/hw04/verification.json.

It does NOT modify any application code. It:
  1. reads existing files (and the saved experiment results),
  2. starts the FastAPI app as a temporary subprocess if nothing is already
     listening on PORT_BASE (and stops it again at the end),
  3. creates ONE temporary fixture through the API to test create/read/update/
     delete, then removes it.

The checks test behavior (status codes, cookie flags, database contents, query
counts), not exact wording. Any random choices use VERIFY_SEED.

Needs the same MYSQL_USER and MYSQL_PASSWORD environment variables the app uses.
Run from the repo root, inside the venv:   python verify_hw04.py
"""

import json
import os
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
APP_DIR = REPO_ROOT / "code" / "web_application"
CLIENT_SRC = APP_DIR / "client" / "src"
HW04 = REPO_ROOT / "reports" / "hw04"
RAW = HW04 / "raw"
VERIFICATION_OUTPUT = HW04 / "verification.json"

SID4 = "9871"
SEED = "9871"
VERIFY_SEED = "269871"
PORT_BASE = 8871
DB_NAME = "s9871_rel"
BASE_URL = f"http://127.0.0.1:{PORT_BASE}"
MODEL_CONFIG = ("qwen3:8b via Ollama, temperature 0.0 (Part 4 RAG generation); "
                "sentence-transformers/all-MiniLM-L6-v2 (embeddings); FastAPI + MySQL 8 via SQLAlchemy; React client")

# The demo account the app seeds at startup (see api_v2.seed_demo_data).
DEMO_EMAIL = "league_admin@example.com"
DEMO_PASSWORD = "GoLions2026!"
REFUSAL = "I cannot answer this question from the provided documents"
PAGE_SIZES = [10, 50, 200]

rng = random.Random(int(VERIFY_SEED))
state = {}                      # values shared between checks (e.g. the session token)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def git(*args):
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=20, cwd=str(REPO_ROOT))
        return r.stdout.strip()
    except Exception:
        return ""


def db_rows(sql, args=()):
    import pymysql
    import pymysql.cursors
    conn = pymysql.connect(host="localhost", user=os.environ.get("MYSQL_USER", "root"),
                           password=os.environ.get("MYSQL_PASSWORD", ""), database=DB_NAME,
                           connect_timeout=5, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())
    finally:
        conn.close()


def api(method, path, token=None, **kwargs):
    # The session cookie is Secure. Browsers exempt localhost, but python-requests does not,
    # so the token is passed explicitly instead of via a cookie jar.
    cookies = {"session_token": token} if token else None
    return requests.request(method, BASE_URL + path, cookies=cookies, timeout=20, **kwargs)


def need_token():
    if not state.get("token"):
        raise RuntimeError("no session token (the login check must pass first)")
    return state["token"]


def server_alive():
    try:
        return requests.get(BASE_URL + "/api/auth/me", timeout=2).status_code in (200, 401)
    except Exception:
        return False


def start_server_if_needed():
    """Reuse a server that is already running; otherwise start one. Returns (process, started)."""
    if server_alive():
        return None, False
    log_path = Path(tempfile.gettempdir()) / "verify_hw04_uvicorn.log"
    state["server_log"] = log_path
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
        cwd=str(APP_DIR), stdout=open(log_path, "w"), stderr=subprocess.STDOUT, env=os.environ.copy())
    deadline = time.time() + 45
    while time.time() < deadline:
        if server_alive() or proc.poll() is not None:
            break
        time.sleep(1)
    return proc, True


def stop_server(proc):
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


def check(name, fn):
    try:
        passed, detail = fn()
        return {"check": name, "passed": bool(passed), "detail": detail}
    except Exception as e:
        return {"check": name, "passed": False, "detail": f"Exception: {type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
def check_required_files():
    required = [
        APP_DIR / "main.py", APP_DIR / "api_v2.py", APP_DIR / "db.py", APP_DIR / "models.py",
        APP_DIR / "query_counter.py", APP_DIR / "seed_n1_data.py", APP_DIR / "measure_n1.py",
        *[CLIENT_SRC / f"{n}.jsx" for n in ("App", "Login", "Home", "CreateRecord", "UpdateRecord", "DeleteRecord")],
        REPO_ROOT / "rag.py", REPO_ROOT / "rescore.py",
        HW04 / "questions.yaml", HW04 / "RUN_LOG.txt", HW04 / "METRICS.md", HW04 / "AI_USE.md", HW04 / "report.pdf",
        HW04 / "sql" / "schema.sql", HW04 / "sql" / "add_index.sql",
        RAW / "n1_measurements.json", RAW / "n1_measurements.csv",
        RAW / "retrieved_top3.json", RAW / "three_config_comparison.json", RAW / "k_sweep.json",
        RAW / "evaluation_table.json", RAW / "run_config.json",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
    if missing:
        return False, f"Missing {len(missing)} of {len(required)}: {missing}"
    return True, f"All {len(required)} required files present."


def check_db_variable_and_schema():
    sys.path.insert(0, str(APP_DIR))
    import db
    if not hasattr(db, "db_session_basede26"):
        return False, "db.py does not define db_session_basede26"
    tables = {list(r.values())[0] for r in db_rows("SHOW TABLES")}
    need = {"fixtures", "fixture_updates", "users", "sessions"}
    if not need <= tables:
        return False, f"Missing tables: {sorted(need - tables)}"
    users = {r["Field"] for r in db_rows("SHOW COLUMNS FROM users")}
    sessions = {r["Field"] for r in db_rows("SHOW COLUMNS FROM sessions")}
    fixtures = {r["Field"] for r in db_rows("SHOW COLUMNS FROM fixtures")}
    if not {"id", "name", "email", "password_hash"} <= users:
        return False, f"users columns: {sorted(users)}"
    if not {"id", "user_id", "created_at", "expires_at"} <= sessions:
        return False, f"sessions columns: {sorted(sessions)}"
    if not {"id", "fixture_name", "teams_players"} <= fixtures:
        return False, f"fixtures columns: {sorted(fixtures)}"
    unique_email = any(r["Column_name"] == "email" and r["Non_unique"] == 0 for r in db_rows("SHOW INDEX FROM users"))
    if not unique_email:
        return False, "users.email is not unique"
    return True, f"db_session_basede26 defined; tables {sorted(need)} present in {DB_NAME}; email unique."


def check_seed_data_present():
    fixtures = db_rows("SELECT COUNT(*) AS n FROM fixtures")[0]["n"]
    updates = db_rows("SELECT COUNT(*) AS n FROM fixture_updates")[0]["n"]
    orphans = db_rows("SELECT COUNT(*) AS n FROM fixture_updates u LEFT JOIN fixtures f ON f.id = u.fixture_id "
                      "WHERE f.id IS NULL")[0]["n"]
    ok = fixtures >= 5000 and updates == 200 and orphans == 0
    return ok, f"fixtures={fixtures} (need >= 5000), fixture_updates={updates} (need 200), orphaned related rows={orphans}"


def check_index_used_by_explain():
    idx = db_rows("SHOW INDEX FROM fixtures WHERE Key_name = 'idx_fixture_name'")
    if not idx:
        return False, "index idx_fixture_name not found on fixtures"
    plan = db_rows("EXPLAIN SELECT * FROM fixtures WHERE fixture_name = 'Lions vs Tigers'")[0]
    ok = plan["key"] == "idx_fixture_name" and plan["type"] in ("ref", "const", "range")
    return ok, f"EXPLAIN: type={plan['type']}, key={plan['key']}, rows={plan['rows']}"


def check_backend_responds():
    r = requests.get(BASE_URL + "/api/auth/me", timeout=5)
    ok = r.status_code == 401
    return ok, f"GET /api/auth/me without a session -> HTTP {r.status_code} on port {PORT_BASE} (expected 401)"


def check_unauthenticated_rejected():
    paths = ["/api/fixtures", "/api/fixtures/1", "/api/fixtures-naive?page_size=10", "/api/fixtures-fixed?page_size=10"]
    codes = {p: requests.get(BASE_URL + p, timeout=10).status_code for p in paths}
    return all(c == 401 for c in codes.values()), f"unauthenticated status codes: {codes}"


def check_login_cookie():
    bad = requests.post(BASE_URL + "/api/auth/login", json={"email": DEMO_EMAIL, "password": "wrong-password"}, timeout=10)
    if bad.status_code != 401:
        return False, f"wrong password returned HTTP {bad.status_code}, expected 401"
    r = requests.post(BASE_URL + "/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=10)
    if r.status_code != 200:
        return False, f"login returned HTTP {r.status_code}"
    header = r.headers.get("set-cookie", "")
    m = re.search(r"session_token=([^;]+)", header)
    if not m:
        return False, "no session_token cookie in the login response"
    token = m.group(1)
    body = r.text.lower()
    problems = []
    if "httponly" not in header.lower():
        problems.append("cookie is not HttpOnly")
    if len(token) < 24 or not re.fullmatch(r"[0-9a-zA-Z_\-]+", token):
        problems.append("token does not look like an opaque random id")
    user = r.json()
    for value in (user.get("email", ""), user.get("name", "")):
        if value and value.lower() in token.lower():
            problems.append("cookie value contains user data")
    if "password" in body or "hash" in body:
        problems.append("login response leaks password data")
    state["token"], state["user_id"] = token, user.get("id")
    if problems:
        return False, "; ".join(problems)
    return True, f"wrong password -> 401; login -> 200; cookie is HttpOnly, opaque ({len(token)} chars), holds no user data"


def check_session_in_mysql():
    token = need_token()
    rows = db_rows("SELECT user_id, expires_at FROM sessions WHERE id = %s", (token,))
    if not rows:
        return False, "the session token from the cookie has no row in the sessions table"
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    ok = rows[0]["user_id"] == state["user_id"] and rows[0]["expires_at"] > utc_now
    return ok, f"sessions row found: user_id={rows[0]['user_id']}, expires_at={rows[0]['expires_at']}"


def check_crud_roundtrip():
    token = need_token()
    name = f"verify-fixture-{rng.randint(100000, 999999)}"
    new_id = None
    steps = []
    try:
        r = api("POST", "/api/fixtures", token, json={"fixture_name": name, "teams_players": "temp A vs temp B"})
        if r.status_code != 200 or "id" not in r.json():
            return False, f"create -> HTTP {r.status_code}"
        new_id = r.json()["id"]; steps.append(f"create id={new_id}")
        g = api("GET", f"/api/fixtures/{new_id}", token)
        if g.status_code != 200 or g.json().get("fixture_name") != name:
            return False, f"read by id failed: HTTP {g.status_code} {g.text[:100]}"
        steps.append("read")
        u = api("PUT", f"/api/fixtures/{new_id}", token, json={"fixture_name": name + "-edited", "teams_players": "temp C vs temp D"})
        row = db_rows("SELECT fixture_name, teams_players FROM fixtures WHERE id = %s", (new_id,))
        if u.status_code != 200 or not row or row[0]["fixture_name"] != name + "-edited" or row[0]["teams_players"] != "temp C vs temp D":
            return False, f"update not persisted in MySQL (HTTP {u.status_code}, row={row})"
        steps.append("update persisted in MySQL")
        d = api("DELETE", f"/api/fixtures/{new_id}", token)
        gone = api("GET", f"/api/fixtures/{new_id}", token)
        left = db_rows("SELECT id FROM fixtures WHERE id = %s", (new_id,))
        if d.status_code != 200 or gone.status_code != 404 or left:
            return False, f"delete failed (HTTP {d.status_code}, then GET -> {gone.status_code}, rows left={len(left)})"
        steps.append("delete removed the row from MySQL")
        new_id = None
        return True, "; ".join(steps)
    finally:
        if new_id is not None:                      # clean up even if a step failed
            try:
                api("DELETE", f"/api/fixtures/{new_id}", token)
            except Exception:
                pass


def check_naive_vs_fixed():
    token = need_token()
    size = rng.choice(PAGE_SIZES)
    n = api("GET", "/api/fixtures-naive", token, params={"page_size": size})
    f = api("GET", "/api/fixtures-fixed", token, params={"page_size": size})
    if n.status_code != 200 or f.status_code != 200:
        return False, f"naive HTTP {n.status_code}, fixed HTTP {f.status_code}"
    nd, fd = n.json(), f.json()
    nq, fq = int(n.headers.get("X-SQL-Query-Count", -1)), int(f.headers.get("X-SQL-Query-Count", -1))
    same = [(x["id"], x["updates"]) for x in nd] == [(x["id"], x["updates"]) for x in fd]
    ok = len(nd) == size and len(fd) == size and same and nq == size + 1 and fq == 2
    return ok, (f"page_size={size}: naive returned {len(nd)} rows with {nq} SQL queries (expected {size + 1}); "
                f"fixed returned {len(fd)} rows with {fq} SQL queries (expected 2); same data={same}")


def check_logout_revokes():
    token = need_token()
    out = api("POST", "/api/auth/logout", token)
    after = api("GET", "/api/fixtures/1", token)
    left = db_rows("SELECT id FROM sessions WHERE id = %s", (token,))
    ok = out.status_code == 200 and after.status_code == 401 and not left
    return ok, f"logout -> {out.status_code}; old token then -> HTTP {after.status_code} (expected 401); sessions rows left={len(left)}"


def check_measurements():
    rows = json.loads((RAW / "n1_measurements.json").read_text(encoding="utf-8"))
    if len(rows) != 180:
        return False, f"expected 180 rows, found {len(rows)}"
    problems, medians = [], {}
    for version in ("naive", "fixed"):
        for size in PAGE_SIZES:
            g = [r for r in rows if r["version"] == version and r["page_size"] == size]
            if len(g) != 30:
                problems.append(f"{version}/{size}: {len(g)} rows, expected 30")
                continue
            expect = size + 1 if version == "naive" else 2
            if any(r["sql_query_count"] != expect for r in g):
                problems.append(f"{version}/{size}: query count not always {expect}")
            medians[(version, size)] = statistics.median(r["latency_ms"] for r in g)
    for size in PAGE_SIZES:
        if (("naive", size) in medians and ("fixed", size) in medians
                and medians[("fixed", size)] >= medians[("naive", size)]):
            problems.append(f"fixed is not faster than naive at page size {size}")
    if problems:
        return False, "; ".join(problems)
    sp = ", ".join(f"{s}: {medians[('naive', s)] / medians[('fixed', s)]:.2f}x" for s in PAGE_SIZES)
    return True, f"180 rows (3 sizes x 2 versions x 30); naive = 1+N queries, fixed = 2; p50 speed-up per page size: {sp}"


def check_react_client():
    problems = []
    app = (CLIENT_SRC / "App.jsx").read_text(encoding="utf-8")
    for route in ('path="/"', 'path="/login"', 'path="/create"', 'path="/update', 'path="/delete'):
        if route not in app:
            problems.append(f"App.jsx missing {route}")
    if "react-router-dom" not in app:
        problems.append("App.jsx does not use react-router-dom")
    if "useState" not in app or "useEffect" not in app:
        problems.append("App.jsx should use useState and useEffect")
    for comp, prop in (("CreateRecord", "onCreate"), ("UpdateRecord", "onUpdate"), ("DeleteRecord", "onDelete")):
        text = (CLIENT_SRC / f"{comp}.jsx").read_text(encoding="utf-8")
        if not re.search(rf"function {comp}\(\{{[^)]*{prop}", text):
            problems.append(f"{comp}.jsx does not take {prop} as a prop")
    if "useState" not in (CLIENT_SRC / "Login.jsx").read_text(encoding="utf-8"):
        problems.append("Login.jsx does not use useState")
    pkg = (APP_DIR / "client" / "package.json").read_text(encoding="utf-8")
    if "react-router-dom" not in pkg:
        problems.append("package.json does not list react-router-dom")
    return (not problems), ("; ".join(problems) if problems else "routes /, /login, /create, /update, /delete; hooks and props present; react-router-dom installed")


def check_rag_results():
    import yaml
    problems = []
    qs = yaml.safe_load((HW04 / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    if len(qs) != 6:
        problems.append(f"{len(qs)} questions, expected 6")
    cfg = json.loads((RAW / "run_config.json").read_text(encoding="utf-8"))
    if cfg.get("chunk_size_chars") != 500 or cfg.get("chunk_overlap_chars") != 50 or cfg.get("top_k") != 3:
        problems.append(f"run_config: chunk/overlap/top_k = {cfg.get('chunk_size_chars')}/{cfg.get('chunk_overlap_chars')}/{cfg.get('top_k')}")
    if len(cfg.get("documents", {})) < 5:
        problems.append("fewer than 5 documents indexed")
    rows = json.loads((RAW / "three_config_comparison.json").read_text(encoding="utf-8"))
    combos = {(r["qid"], r["config"]) for r in rows}
    if len(rows) != 18 or len(combos) != 18:
        problems.append(f"comparison has {len(rows)} rows / {len(combos)} distinct (question, config) pairs, expected 18")
    for r in rows:
        if r["config"] == "C" and r["qid"] in ("q5", "q6") and REFUSAL.lower() not in r["answer"].lower():
            problems.append(f"config C did not refuse {r['qid']}")
    sweep = json.loads((RAW / "k_sweep.json").read_text(encoding="utf-8"))
    if {1, 3, 5} - {r["k"] for r in sweep}:
        problems.append("k sweep does not cover k = 1, 3 and 5")
    ev = json.loads((RAW / "evaluation_table.json").read_text(encoding="utf-8"))
    if set(ev.get("summary", {})) != {"A", "B", "C"}:
        problems.append("evaluation summary should cover configs A, B and C")
    return (not problems), ("; ".join(problems) if problems else
            f"6 questions, {len(cfg['documents'])} documents, 18 comparison rows, k sweep over 1/3/5, config C refused Q5 and Q6, evaluation table present")


# ---------------------------------------------------------------------------
def ollama_model_available():
    try:
        tags = requests.get("http://localhost:11434/api/tags", timeout=3).json()
        return any(m.get("name", "").startswith("qwen3:8b") for m in tags.get("models", []))
    except Exception:
        return None


def main():
    if "MYSQL_PASSWORD" not in os.environ:
        print("WARNING: MYSQL_USER / MYSQL_PASSWORD are not set in this terminal, so the database checks will "
              "fail.\n         Set them first, e.g. in PowerShell:  $env:MYSQL_USER=\"hw4app\"; "
              "$env:MYSQL_PASSWORD=\"<your password>\"\n")
    commit = git("rev-parse", "HEAD") or "unknown"
    # ignore this script's own output file, which is expected to change between runs
    dirty = [l for l in git("status", "--porcelain").splitlines()
             if l.strip() and not l.strip().endswith("reports/hw04/verification.json")]
    proc, started = start_server_if_needed()
    try:
        checks = [
            check("required_files_present", check_required_files),
            check("db_variable_name_and_schema", check_db_variable_and_schema),
            check("seed_data_present", check_seed_data_present),
            check("index_present_and_used_by_explain", check_index_used_by_explain),
            check("backend_responds_on_port_base", check_backend_responds),
            check("unauthenticated_requests_rejected", check_unauthenticated_rejected),
            check("login_cookie_is_httponly_and_opaque", check_login_cookie),
            check("session_stored_server_side_in_mysql", check_session_in_mysql),
            check("crud_roundtrip_persists_in_mysql", check_crud_roundtrip),
            check("naive_and_fixed_return_same_data_with_expected_query_counts", check_naive_vs_fixed),
            check("logout_revokes_the_session", check_logout_revokes),
            check("n1_measurements_complete_and_consistent", check_measurements),
            check("react_client_routes_hooks_and_props", check_react_client),
            check("rag_results_complete_including_refusals", check_rag_results),
        ]
    finally:
        stop_server(proc)

    report = {
        "homework": "HW4",
        "sid4": SID4,
        "commit_hash": commit,
        "working_tree_clean": not dirty,
        "uncommitted_paths": [l[3:] for l in dirty][:20],
        "model_config": MODEL_CONFIG,
        "ollama_qwen3_8b_available": ollama_model_available(),
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "port_base": PORT_BASE,
        "database": DB_NAME,
        "backend_started_by_script": started,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "all_checks_passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
    VERIFICATION_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    VERIFICATION_OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for c in checks:
        print(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['check']}\n        {c['detail']}")
    print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed.  Written to: {VERIFICATION_OUTPUT}")
    if not report["all_checks_passed"] and state.get("server_log") and started:
        print(f"(server log for debugging: {state['server_log']})")
    sys.exit(0 if report["all_checks_passed"] else 1)


if __name__ == "__main__":
    main()