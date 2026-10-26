"""
DATA-260 Homework 7 - verify_hw07.py
A self-check smoke test confirming the HW7 system works. Writes its results to reports/hw07/verification.json.

It does NOT modify any application code. It:
  1. checks that every required file exists,
  2. starts the JWT/RBAC FastAPI app (code/web_application, port PORT_BASE = 8871) as a temporary subprocess if nothing is listening
     there, and stops it again at the end; it only reads data and makes calls that are refused or harmless,
  3. runs each part's offline test-suite as a subprocess and requires every check in it to pass,
  4. makes two REAL model calls (Ollama qwen3:8b, sampling seed = VERIFY_SEED): the hand-written agent loop (Part 2) and the Bay Wheels
     agent (Part 4, live pricing page, pay-per-use scenario),
  5. checks the Part 5 tool boundary and the Part 6 safety gate directly.

The checks test behavior (status codes, database state, counts, refused writes), not exact wording.
Needs MySQL (s9871_rel) and Ollama with qwen3:8b, plus internet for the Part 4 live pricing page.
Run from the repo root, inside the venv:   python verify_hw07.py        (add --fast to skip the two real-model checks)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
HW07 = REPO_ROOT / "reports" / "hw07"
APP_DIR = REPO_ROOT / "code" / "web_application"
VERIFICATION_OUTPUT = HW07 / "verification.json"

SID4, SEED, VERIFY_SEED, PORT_BASE = "9871", "9871", "269871", 8871
BASE_URL = f"http://127.0.0.1:{PORT_BASE}"
MODEL_CONFIG = ("qwen3:8b via Ollama (thinking off, temperature 0, sampling seed = VERIFY_SEED during this run); sentence-transformers/all-MiniLM-L6-v2 "
                "(policy retrieval); FastAPI + MySQL (s9871_rel) with JWT bearer auth; LangChain create_agent (Part 4); hand-written loop (Parts 2, 3, 6)")
PRICING_URL = "https://www.lyft.com/bikes/bay-wheels/pricing"

REQUIRED_FILES = [
    "verify_hw07.py", "pyproject.toml", ".pre-commit-config.yaml",
    "code/web_application/auth_jwt.py", "code/web_application/migrate_hw07.py", "code/web_application/test_jwt_auth.py",
    "code/tool_schemas.py", "code/agent_loop.py", "code/agent_cases.py", "code/agent_cases/verification_cases.json", "code/measure_tool_reliability.py",
    "code/test_agent_loop.py", "code/agent_verifiers.py", "code/reflexion.py", "code/test_reflexion.py", "code/measure_reflexion.py",
    "code/bikeshare/tools.py", "code/bikeshare/agent.py", "code/bikeshare/costs.py", "code/bikeshare/server.py", "code/bikeshare/static/index.html",
    "code/bikeshare/test_bikeshare.py", "code/bikeshare/test_ui.py", "code/bikeshare/data/scenario_membership_wins.csv",
    "code/bikeshare/data/scenario_payperuse_wins.csv", "code/bikeshare/attacks.py", "code/bikeshare/run_attacks.py", "code/bikeshare/test_security.py",
    "code/agent_cases/hostile_pricing_page.html", "code/agent_cases/attack_cases.json", "code/file_tools.py", "code/test_file_tools.py", "code/run_part6_test.py",
    "reports/hw07/RUN_LOG.txt", "reports/hw07/METRICS.md", "reports/hw07/AI_USE.md", "reports/hw07/Patel_HW07_report.tex", "reports/hw07/Patel_HW7.pdf", "reports/hw07/report.pdf", "reports/hw07/part5/THREAT_MODEL.md",
    "reports/hw07/part4/EVIDENCE.md", "reports/hw07/raw/part3_summary.json", "reports/hw07/raw/part4_v4_measure_summary.json",
    "reports/hw07/raw/part5_v1_attack_summary.json", "reports/hw07/raw/part5_v2_attack_summary.json",
]
SCREENSHOTS = ["part1_login_success", "part1_login_401", "part1_me_no_token_401", "part1_create_reader_403", "part1_delete_moderator_200",
               "part1_lint_1a_errors_before_commit", "part1_lint_2_fixed_and_committed", "part4_ui_membership_wins", "part4_ui_payperuse_wins"]
state = {}


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


def alive():
    try:
        return requests.get(BASE_URL + "/auth/me", timeout=2).status_code in (401, 200)
    except Exception:
        return False


def start_server_if_needed():
    if alive():
        return None
    log = open(Path(tempfile.gettempdir()) / "verify_hw07_uvicorn.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)], cwd=str(APP_DIR), stdout=log,
                            stderr=subprocess.STDOUT, env=os.environ.copy())
    for _ in range(60):
        if alive() or proc.poll() is not None:
            break
        time.sleep(1)
    return proc


def run_suite(rel_path, expect_min):
    """Run a test script as a subprocess; it must exit 0 and report 'N/N checks passed' with N >= expect_min."""
    r = subprocess.run([sys.executable, rel_path], capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=900, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    m = re.findall(r"(\d+)/(\d+) checks passed", r.stdout)
    ok = r.returncode == 0 and bool(m) and m[-1][0] == m[-1][1] and int(m[-1][1]) >= expect_min
    return ok, f"{rel_path}: exit {r.returncode}, {m[-1][0]}/{m[-1][1]} checks passed" if m else f"{rel_path}: exit {r.returncode}; no summary line. {r.stdout[-200:]} {r.stderr[-200:]}"


def mysql_scalar(sql):
    sys.path.insert(0, str(APP_DIR))
    import logging

    logging.disable(logging.CRITICAL)
    from db import engine
    from sqlalchemy import text

    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


# ------------------------------------------------------------------------------------------------ checks
def check_files():
    missing = [f for f in REQUIRED_FILES if not (REPO_ROOT / f).exists()]
    shots = [s for s in SCREENSHOTS if not (HW07 / "screenshots" / f"{s}.png").exists()]
    return (not missing and not shots, f"All {len(REQUIRED_FILES)} required files and {len(SCREENSHOTS)} key screenshots present." if not (missing or shots)
            else f"Missing files {missing}; missing screenshots {shots}")


def check_p1_auth_flow():
    bad = requests.post(BASE_URL + "/auth/login", json={"username": "writer_user", "password": "wrong-password"}, timeout=15)
    good = requests.post(BASE_URL + "/auth/login", json={"username": "reader_user", "password": "Reader2026!"}, timeout=15)
    token = good.json().get("access_token", "") if good.status_code == 200 else ""
    state["reader"] = token
    me = requests.get(BASE_URL + "/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    none = requests.get(BASE_URL + "/auth/me", timeout=15)
    tampered = requests.get(BASE_URL + "/auth/me", headers={"Authorization": f"Bearer {token[:-4]}AAAA"}, timeout=15)
    ok = (bad.status_code == 401 and good.status_code == 200 and token.count(".") == 2 and me.status_code == 200 and me.json().get("role") == "reader"
          and none.status_code == 401 and tampered.status_code == 401)
    return ok, f"wrong password {bad.status_code}; login {good.status_code} (JWT with 3 parts: {token.count('.') == 2}); /auth/me with token {me.status_code} role={me.json().get('role') if me.ok else None}; no token {none.status_code}; tampered token {tampered.status_code}"


def check_p1_rbac_and_db():
    before = mysql_scalar("SELECT COUNT(*) FROM fixtures")
    tok = lambda u, p: requests.post(BASE_URL + "/auth/login", json={"username": u, "password": p}, timeout=15).json()["access_token"]  # noqa: E731
    h = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
    reader_del = requests.delete(BASE_URL + "/api/fixtures/999999999", headers=h(state["reader"]), timeout=15)
    writer_del = requests.delete(BASE_URL + "/api/fixtures/999999999", headers=h(tok("writer_user", "Writer2026!")), timeout=15)
    anon_del = requests.delete(BASE_URL + "/api/fixtures/999999999", timeout=15)
    mod_del = requests.delete(BASE_URL + "/api/fixtures/999999999", headers=h(tok("moderator_user", "Moderator2026!")), timeout=15)
    reader_list = requests.get(BASE_URL + "/api/teams", headers=h(state["reader"]), timeout=15)
    after = mysql_scalar("SELECT COUNT(*) FROM fixtures")
    hashes = [r for r in [mysql_scalar("SELECT COUNT(*) FROM users WHERE password_hash NOT LIKE '$2%'")]]
    ok = (reader_del.status_code == 403 and writer_del.status_code == 403 and anon_del.status_code == 401 and mod_del.status_code == 404
          and reader_list.status_code == 200 and before == after and hashes[0] == 0)
    return ok, (f"DELETE by reader {reader_del.status_code}, writer {writer_del.status_code}, anonymous {anon_del.status_code}, moderator {mod_del.status_code} (404 = allowed through, row absent); "
                f"reader GET /api/teams {reader_list.status_code}; fixtures in MySQL before/after {before}/{after}; users with a non-bcrypt hash: {hashes[0]}")


def check_p2_real_agent():
    sys.path[:0] = [str(REPO_ROOT / "code"), str(REPO_ROOT / "src")]
    from agent_loop import run_agent
    from model_client import ModelClient

    out = run_agent("Which team hosts the most fixtures? Use the tools.", model=ModelClient(model="qwen3:8b", temperature=0.0, reasoning=False, seed=int(VERIFY_SEED)),
                    log_path=Path(tempfile.mkdtemp()) / "run.jsonl")
    ok = out["stop_reason"] == "final_answer" and out["tool_calls_executed"] >= 1 and bool(out["final_answer"]) and out["tool_calls_invalid"] == 0
    return ok, f"stop_reason={out['stop_reason']}, tool calls executed={out['tool_calls_executed']}, invalid={out['tool_calls_invalid']}, steps={out['steps']}"


def check_p3_saved_results():
    s = json.loads((HW07 / "raw" / "part3_summary.json").read_text(encoding="utf-8"))
    v = s["verifier_vs_oracle_all_attempts"]
    ok = s["overall"]["original"]["runs"] == 36 and s["overall"]["reflexion"]["runs"] == 36 and "false_rejections" in v and set(s["stop_reasons"]) <= {"success", "budget_exhausted", "human_review"}
    return ok, f"36 paired runs recorded; stop reasons {s['stop_reasons']}; verifier vs database oracle: {v['false_rejections']} false rejections, {v['false_acceptances']} false acceptances"


def check_p4_tools_boundary():
    sys.path.insert(0, str(REPO_ROOT / "code" / "bikeshare"))
    from tools import CsvSql, calculator

    db = CsvSql(REPO_ROOT / "code" / "bikeshare" / "data" / "scenario_payperuse_wins.csv")
    n = db.run("SELECT COUNT(*) AS n FROM trips")["data"]["rows"][0]["n"]
    refused = [s for s in ("DELETE FROM trips", "DROP TABLE trips", "WITH x AS (SELECT 1) DELETE FROM trips", "SELECT 1; DELETE FROM trips") if not db.run(s)["success"]]
    after = db.run("SELECT COUNT(*) AS n FROM trips")["data"]["rows"][0]["n"]
    calc_ok = calculator("29 * 48")["data"]["value"] == 1392.0 and not calculator("__import__('os')")["success"]
    return n >= 500 and len(refused) == 4 and after == n and calc_ok, f"scenario rows={n}; 4/4 write attempts refused={len(refused) == 4}; rows after={after}; calculator ok={calc_ok}"


def check_p4_live_agent():
    sys.path.insert(0, str(REPO_ROOT / "code" / "bikeshare"))
    import hashlib

    from agent import run_bike_agent
    from langchain_ollama import ChatOllama

    tmp = Path(tempfile.mkdtemp(prefix="verify_hw07_snap_"))
    model = ChatOllama(model="qwen3:8b", temperature=0.0, seed=int(VERIFY_SEED), reasoning=False, num_ctx=8192, num_predict=3000, client_kwargs={"timeout": 150})
    out = run_bike_agent(REPO_ROOT / "code" / "bikeshare" / "data" / "scenario_payperuse_wins.csv", PRICING_URL, model=model, snapshot_dir=tmp, run_id="verify_hw07",
                         scenario="payperuse_wins")
    tools_used = {e["tool"] for e in out["timeline"] if e["kind"] == "tool_call"}
    snap = out["snapshot"] or {}
    snap_ok = bool(snap) and hashlib.sha256(Path(snap["path"]).read_bytes()).hexdigest() == snap["sha256"] and len(snap["sha256"]) == 64
    decision = (out["result"] or {}).get("decision")
    ok = (out["stop_reason"] == "final_answer" and tools_used == {"csv_sql", "policy_retriever", "calculator"} and snap_ok
          and decision == out["reference"]["decision"])
    return ok, (f"stop_reason={out['stop_reason']}, steps={out['steps']}, {out['total_time_s']} s, tools used={sorted(tools_used)}, snapshot sha256 matches its saved text={snap_ok}, "
                f"decision={decision!r} (reference {out['reference']['decision']!r}), all numbers match the independent recomputation={out['verification'].get('all_ok')}")


def check_p5_saved_results():
    s = json.loads((HW07 / "raw" / "part5_v1_attack_summary.json").read_text(encoding="utf-8"))["cells"]
    ok = len(s) == 9 and all(c["runs"] == 5 for c in s.values()) and s["override/before"]["attack_succeeded"] >= 1
    cases = json.loads((REPO_ROOT / "code" / "agent_cases" / "attack_cases.json").read_text(encoding="utf-8"))
    return ok and set(cases["attacks"]) == {"override", "misuse", "exfil"}, f"9 cells x 5 runs recorded; override/before succeeded {s['override/before']['attack_succeeded']}/5; fixture + 3 attack cases saved"


def check_p6_gate():
    sys.path.insert(0, str(REPO_ROOT / "code"))
    from file_tools import confirm_bash, is_destructive

    passes = ["ls -la", "cat notes.txt", "grep -n DEBUG app.py", "git status", "echo hello"]
    blocks = ["rm -rf ./build", "sudo apt install foo", "chmod 777 app.py", "dd if=/dev/zero of=/dev/sda", "ls -la; rm -rf /"]
    good = [c for c in passes if confirm_bash(c)["allowed"] and not is_destructive(c)]
    bad = [c for c in blocks if not confirm_bash(c)["allowed"] and is_destructive(c)]
    confirmed = confirm_bash("rm -rf ./build", confirm=lambda c: True)["allowed"] and not confirm_bash("rm -rf ./build", auto_approve=True)["allowed"]
    return len(good) == 5 and len(bad) == 5 and confirmed, f"{len(good)}/5 allowed, {len(bad)}/5 blocked; destructive allowed only with explicit confirmation (auto_approve does not apply): {confirmed}"


def check_ruff():
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "code/bikeshare", "code/file_tools.py", "code/test_file_tools.py", "code/run_part6_test.py", "code/agent_loop.py",
                        "code/reflexion.py", "code/agent_verifiers.py", "code/tool_schemas.py", "code/web_application/auth_jwt.py", "verify_hw07.py"],
                       capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode == 0, (r.stdout.strip().splitlines() or [""])[-1]


def main():
    fast = "--fast" in sys.argv          # skips the two real-model checks (used only to test this script against broken states)
    started = datetime.now().isoformat(timespec="seconds")
    print("verify_hw07 run at", started, flush=True)
    server = start_server_if_needed()
    checks = []
    plan = [("required files and screenshots exist", check_files),
            ("Part 1: login 401 on a wrong password, JWT on success, /auth/me needs a valid token (no token / tampered token -> 401)", check_p1_auth_flow),
            ("Part 1: role-based access (reader/writer 403, anonymous 401, moderator allowed) and MySQL unchanged, bcrypt hashes only", check_p1_rbac_and_db),
            ("Part 2: tool-schema and agent-loop test-suite (offline)", lambda: run_suite("code/test_agent_loop.py", 58)),
            ("Part 2: the hand-written agent loop answers a question with the real model and real tools", check_p2_real_agent),
            ("Part 3: Reflexion verifier and bounded-loop test-suite (offline)", lambda: run_suite("code/test_reflexion.py", 47)),
            ("Part 3: the saved 36-run comparison is complete and reports false rejections", check_p3_saved_results),
            ("Part 4: tool and agent test-suite (offline)", lambda: run_suite("code/bikeshare/test_bikeshare.py", 92)),
            ("Part 4: csv_sql refuses writes and the calculator is safe, on the real scenario file", check_p4_tools_boundary),
            ("Part 4: the UI and API paths (real server + headless browser, no model)", lambda: run_suite_ui()),
            ("Part 4: the agent answers the pay-per-use scenario with the real model on the live pricing page", check_p4_live_agent),
            ("Part 5: injection defenses and attack-scoring test-suite (offline, scripted obedient model)", lambda: run_suite("code/bikeshare/test_security.py", 33)),
            ("Part 5: saved attack results and the hostile fixture are complete", check_p5_saved_results),
            ("Part 6: file-tool and safety-gate test-suite", lambda: run_suite("code/test_file_tools.py", 75)),
            ("Part 6: the 5-pass / 5-block safety-gate contract, directly", check_p6_gate),
            ("Ruff passes on the HW7 code", check_ruff)]
    try:
        for name, fn in plan:
            if fast and fn in (check_p2_real_agent, check_p4_live_agent):
                continue
            print(f"... {name}", flush=True)
            r = check(name, fn)
            print(f"    [{'PASS' if r['passed'] else 'FAIL'}] {r['detail'][:300]}", flush=True)
            checks.append(r)
    finally:
        if server:
            server.terminate()
    passed = sum(c["passed"] for c in checks)
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if not ln.startswith("??") and "__pycache__" not in ln]
    out = {"homework": 7, "sid4": SID4, "commit_hash": git("rev-parse", "HEAD"), "tracked_files_modified_since_commit": dirty,
           "model_config": MODEL_CONFIG, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "port_base": PORT_BASE, "run_at": started,
           "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    VERIFICATION_OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"\n{passed}/{len(checks)} checks passed -> {VERIFICATION_OUTPUT}")
    sys.exit(0 if out["all_passed"] else 1)


def run_suite_ui():
    # test_ui.py --skip-run starts its own server on 8872 and needs no model; it prints "N/N checks passed"
    r = subprocess.run([sys.executable, "code/bikeshare/test_ui.py", "--skip-run"], capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    m = re.findall(r"(\d+)/(\d+) checks passed", r.stdout)
    return r.returncode == 0 and bool(m) and m[-1][0] == m[-1][1] and int(m[-1][1]) >= 13, f"test_ui.py --skip-run: exit {r.returncode}, {m[-1][0]}/{m[-1][1]} checks passed" if m else f"exit {r.returncode}: {r.stdout[-200:]}"


if __name__ == "__main__":
    main()
