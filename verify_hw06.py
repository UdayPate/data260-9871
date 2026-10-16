"""
DATA-260 Homework 6 - verify_hw06.py
A self-check smoke test confirming the HW6 system works. Writes its results to
reports/hw06/verification.json.

It does NOT modify any application code. It:
  1. reads existing files and the saved experiment results,
  2. starts the FastAPI app (code/doc_api) as a temporary subprocess if nothing is already
     listening on PORT_BASE, and stops it again at the end,
  3. creates TEMPORARY data only: one fixture, one throwaway chat user (all its Mongo documents
     are deleted at the end) and temp MEMORY.md files in the OS temp folder - the real MEMORY.md
     is never touched.

The checks test behavior (status codes, database contents, counts, rule compliance), not exact
wording. The model's sampling seed is set to VERIFY_SEED during the run and restored afterwards.

Needs MongoDB on localhost:27017 (docker container s9871-mongo) and Ollama with qwen3:8b.
Run from the repo root, inside the venv:   python verify_hw06.py
"""

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
APP_DIR = REPO_ROOT / "code" / "doc_api"
HW06 = REPO_ROOT / "reports" / "hw06"
RAW = HW06 / "raw"
VERIFICATION_OUTPUT = HW06 / "verification.json"

SID4 = "9871"
SEED = "9871"
VERIFY_SEED = "269871"
PORT_BASE = 8871
DB_NAME = "s9871_doc"
BASE_URL = f"http://127.0.0.1:{PORT_BASE}"
MONGO_URI = "mongodb://localhost:27017"
MODEL_CONFIG = ("qwen3:8b via Ollama (thinking off, temperature 0.3, sampling seed = VERIFY_SEED during this run); "
                "sentence-transformers/all-MiniLM-L6-v2 (embeddings); FastAPI + MongoDB 7 via PyMongo; "
                "file memory = AGENT.md + MEMORY.md")

rng = random.Random(int(VERIFY_SEED))
state = {}
TEMP_USER = f"verify_hw06_{rng.randrange(10**6):06d}"

REQUIRED_FILES = [
    "AGENT.md", "MEMORY.md", "verify_hw06.py",
    "code/doc_api/config.py", "code/doc_api/db.py", "code/doc_api/schemas.py", "code/doc_api/routes.py",
    "code/doc_api/main.py", "code/doc_api/memory.py", "code/doc_api/chat_routes.py",
    "code/doc_api/embeddings.py", "code/doc_api/llm.py", "code/doc_api/tokens.py",
    "code/doc_api/file_memory.py", "code/doc_api/file_routes.py", "code/doc_api/run_part3_sweep.py",
    "code/doc_api/analyze_part3.py", "code/doc_api/part3_conversation.json", "code/doc_api/static/chat.html",
    "code/doc_api/verify_agent_md.py", "src/model_client.py",
    "reports/hw06/RUN_LOG.txt", "reports/hw06/METRICS.md", "reports/hw06/AI_USE.md",
    "reports/hw06/memory_probes.yaml", "reports/hw06/Patel_HW06_report.tex", "reports/hw06/report.pdf",
    "reports/hw06/raw/part3_turns.csv", "reports/hw06/raw/part3_probes.json", "reports/hw06/raw/part3_summary.json",
    "reports/hw06/raw/part3_cost.json", "reports/hw06/raw/part2_memory_uday_demo.json",
    "reports/hw06/raw/part2_aggregate_uday_demo.json", "reports/hw06/raw/part4_agent_md_verification.json",
    "reports/hw06/raw/part4_consolidation_result.json", "reports/hw06/part4/MEMORY_original_55lines.md",
    "reports/hw06/part4/MEMORY_consolidated.md", "reports/hw06/part4/ground_truth.json",
]
SCREENSHOTS = ["part1_post_create", "part1_get_all", "part1_get_one", "part1_put_update", "part1_delete",
               "part1_validation_422", "part1_get_404", "part1_compass_fixtures", "part1_compass_validation",
               "part2_chat_ui", "part2_get_memory", "part2_get_aggregate", "part2_compass_messages",
               "part2_compass_summaries", "part2_compass_episodes"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def git(*args):
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=20, cwd=str(REPO_ROOT))
        return r.stdout.strip()
    except Exception:
        return ""


def mongo_db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000, tz_aware=True)[DB_NAME]


def api(method, path, **kwargs):
    return requests.request(method, BASE_URL + path, timeout=300, **kwargs)


def server_alive():
    try:
        return requests.get(BASE_URL + "/api/health", timeout=2).status_code == 200
    except Exception:
        return False


def start_server_if_needed():
    """Reuse a server that is already running; otherwise start one. Returns (process, started)."""
    if server_alive():
        return None, False
    log_path = Path(tempfile.gettempdir()) / "verify_hw06_uvicorn.log"
    state["server_log"] = log_path
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
        cwd=str(APP_DIR), stdout=open(log_path, "w"), stderr=subprocess.STDOUT, env=os.environ.copy())
    deadline = time.time() + 60
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


def ollama_model_available():
    try:
        tags = requests.get("http://localhost:11434/api/tags", timeout=3).json()
        return any(m.get("name", "").startswith("qwen3:8b") for m in tags.get("models", []))
    except Exception:
        return None


def file_memory_module():
    """Import file_memory in-process with temp paths so the real MEMORY.md can never be modified."""
    if "fm" in state:
        return state["fm"]
    tmp = Path(tempfile.mkdtemp(prefix="verify_hw06_"))
    state["tmp"] = tmp
    os.environ["FILE_MEMORY_PATH"] = str(tmp / "MEMORY.md")
    os.environ["FILE_MEMORY_BACKUP_DIR"] = str(tmp / "backups")
    sys.path.insert(0, str(APP_DIR))
    import config
    import file_memory
    config.settings["LLM_SEED"] = int(VERIFY_SEED)
    state["fm"], state["config"] = file_memory, config
    return file_memory


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
def check_required_files():
    missing = [f for f in REQUIRED_FILES if not (REPO_ROOT / f).exists()]
    shots = [s for s in SCREENSHOTS if not (HW06 / "screenshots" / f"{s}.png").exists()]
    return (not missing and not shots,
            f"All {len(REQUIRED_FILES)} required files and {len(SCREENSHOTS)} screenshots present." if not missing and not shots
            else f"Missing files {missing}; missing screenshots {shots}")


def check_mongo_and_schema():
    db = mongo_db()
    db.client.admin.command("ping")
    names = set(db.list_collection_names())
    need = {"fixtures", "messages", "summaries", "episodes"}
    opts = db["fixtures"].options()
    schema = opts.get("validator", {}).get("$jsonSchema", {})
    props = schema.get("properties", {})
    ok = (need <= names and "fixture_name" in schema.get("required", [])
          and props.get("fixture_name", {}).get("maxLength") == 100
          and len(props.get("category", {}).get("enum", [])) == 4 and len(props.get("status", {}).get("enum", [])) >= 3)
    return ok, f"collections {sorted(names & need)} in {DB_NAME}; fixtures validator required={schema.get('required')}, name maxLength={props.get('fixture_name', {}).get('maxLength')}"


def check_backend_responds():
    r = api("GET", "/api/health")
    return r.status_code == 200 and r.json().get("db") == DB_NAME, f"GET /api/health -> {r.status_code} {r.text[:80]}"


def check_fixture_crud_roundtrip():
    from bson import ObjectId
    col = mongo_db()["fixtures"]
    body = {"fixture_name": "verify_hw06 temp fixture", "description": "temporary", "category": "Soccer",
            "match_date": "2026-12-01T10:00:00Z"}
    r = api("POST", "/api/fixtures", json=body)
    if r.status_code != 201:
        return False, f"POST -> {r.status_code} {r.text[:120]}"
    fid = r.json()["id"]
    try:
        doc = col.find_one({"_id": ObjectId(fid)})
        steps = {"create persisted in Mongo": doc is not None and doc["status"] == "scheduled"}
        steps["GET by id 200"] = api("GET", f"/api/fixtures/{fid}").status_code == 200
        steps["listed"] = any(f["id"] == fid for f in api("GET", "/api/fixtures").json())
        u = api("PUT", f"/api/fixtures/{fid}", json={**body, "status": "completed"})
        doc = col.find_one({"_id": ObjectId(fid)})
        steps["PUT persisted"] = u.status_code == 200 and doc["status"] == "completed" and doc["updated_at"] >= doc["created_at"]
    finally:
        d = api("DELETE", f"/api/fixtures/{fid}")
    steps["DELETE 204 and gone from Mongo"] = d.status_code == 204 and col.find_one({"_id": ObjectId(fid)}) is None
    return all(steps.values()), json.dumps(steps)


def check_fixture_validation():
    base = {"fixture_name": "x", "category": "Soccer", "match_date": "2026-12-01T10:00:00Z"}
    codes = {
        "missing name": api("POST", "/api/fixtures", json={k: v for k, v in base.items() if k != "fixture_name"}).status_code,
        "101-char name": api("POST", "/api/fixtures", json={**base, "fixture_name": "x" * 101}).status_code,
        "bad category": api("POST", "/api/fixtures", json={**base, "category": "Curling"}).status_code,
        "bad date": api("POST", "/api/fixtures", json={**base, "match_date": "tuesday"}).status_code,
        "unknown id": api("GET", "/api/fixtures/000000000000000000000000").status_code,
        "malformed id": api("GET", "/api/fixtures/not-an-id").status_code,
    }
    want = {"missing name": 422, "101-char name": 422, "bad category": 422, "bad date": 422, "unknown id": 404, "malformed id": 400}
    return codes == want, f"status codes {codes}"


def check_chat_memory_pipeline():
    if ollama_model_available() is not True:
        return False, "Ollama / qwen3:8b not available on localhost:11434"
    db = mongo_db()
    sid = None
    replies = []
    for msg in ("Hi, I'm Verifier and I coach the Temp Hawks, an under-10 soccer team.",
                "Remember that we practice on Wednesdays.",
                "Which team do I coach?"):
        body = {"user_id": TEMP_USER, "message": msg, **({"session_id": sid} if sid else {})}
        r = api("POST", "/api/chat", json=body)
        if r.status_code != 200:
            return False, f"POST /api/chat -> {r.status_code} {r.text[:150]}"
        j = r.json()
        sid = j["session_id"]
        replies.append(j)
    last = replies[-1]
    mu, usage = last["memory_used"], last["usage"]
    eps = list(db["episodes"].find({"user_id": TEMP_USER}))
    steps = {
        "every turn returned a non-empty reply": all(isinstance(x["reply"], str) and x["reply"].strip() for x in replies),
        "short-term window grew (turn 3 used 4 messages)": mu["short_term_count"] == 4,
        "response lists memory_used keys": {"short_term_messages", "long_term_summary", "episodic_facts"} <= set(mu),
        "messages persisted (3 user + 3 assistant)": db["messages"].count_documents({"user_id": TEMP_USER}) == 6,
        "episodes have 384-float embeddings and importance in [0,1]": all(len(e["embedding"]) == 384 and 0 <= e["importance"] <= 1 for e in eps),
        "token usage recorded": usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0 and usage["request_latency_ms"] > 0,
        "usage_log row written": db["usage_log"].count_documents({"user_id": TEMP_USER}) == 3,
    }
    state["chat_ok"] = all(steps.values())
    return all(steps.values()), json.dumps(steps) + f"; episodes stored: {len(eps)}"


def check_memory_endpoints():
    db = mongo_db()
    if db["messages"].count_documents({"user_id": TEMP_USER}) == 0:
        return False, "no chat data (the chat check must pass first)"
    m = api("GET", f"/api/memory/{TEMP_USER}")
    a = api("GET", f"/api/aggregate/{TEMP_USER}")
    missing = api("GET", "/api/memory/no_such_user_verify_hw06")
    n_msgs = db["messages"].count_documents({"user_id": TEMP_USER})
    steps = {"memory 200 with expected keys": m.status_code == 200 and {"messages", "latest_session_summary", "latest_lifetime_summary", "episodes"} <= set(m.json()),
             "memory returns the stored messages (<=16)": len(m.json()["messages"]) == min(16, n_msgs),
             "aggregate daily counts sum to stored messages": a.status_code == 200 and sum(d["count"] for d in a.json()["daily_message_counts"]) == n_msgs,
             "unknown user -> 404": missing.status_code == 404}
    return all(steps.values()), json.dumps(steps)


def check_read_only_chat_writes_nothing():
    db = mongo_db()
    before = [db[c].count_documents({"user_id": TEMP_USER}) for c in ("messages", "episodes", "summaries")]
    sid = db["messages"].find_one({"user_id": TEMP_USER})
    if sid is None:
        return False, "no chat data (the chat check must pass first)"
    r = api("POST", "/api/chat", json={"user_id": TEMP_USER, "session_id": sid["session_id"],
                                       "message": "What day do we practice?", "read_only": True})
    after = [db[c].count_documents({"user_id": TEMP_USER}) for c in ("messages", "episodes", "summaries")]
    return r.status_code == 200 and bool(r.json()["reply"].strip()) and before == after, f"counts before {before}, after {after}"


def check_chat_validation():
    codes = [api("POST", "/api/chat", json=b).status_code for b in
             ({"user_id": TEMP_USER, "message": ""}, {"message": "hi"}, {"user_id": "bad user!", "message": "hi"})]
    return codes == [422, 422, 422], f"status codes {codes}"


def check_part3_results():
    import csv
    import statistics
    import yaml
    summary = json.loads((RAW / "part3_summary.json").read_text(encoding="utf-8"))
    runs = summary["runs"]
    cost = json.loads((RAW / "part3_cost.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(RAW / "part3_turns.csv", encoding="utf-8")))
    probes = json.loads((RAW / "part3_probes.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load((HW06 / "memory_probes.yaml").read_text(encoding="utf-8"))
    settings = {r["setting"] for r in runs}
    cheapest_eligible = min(cost["eligible_for_best"], key=lambda s: cost["settings"][s]["cost_10k_convos_all_calls_usd"])
    top = max(v["mean_probe_score"] for v in cost["settings"].values())
    steps = {
        "4 settings x 3 runs": settings == {"N4", "N12", "N30", "COMPRESS"} and len(runs) == 12,
        "360 per-turn rows (4 x 3 x 30), tokens positive": len(rows) == 360 and all(int(r["reply_prompt_tokens"]) > 0 for r in rows),
        "5 probes in memory_probes.yaml with a 1-5 rubric": len(spec["probes"]) == 5 and sorted(spec["scoring"]["rubric"]) == [1, 2, 3, 4, 5],
        "60 probe answers scored within 1-5": len(probes) == 60 and all(1 <= p["score"] <= 5 for p in probes),
        "mean prompt tokens recomputed from the CSV matches summary": all(
            abs(statistics.fmean(float(r["reply_prompt_tokens"]) for r in rows if r["setting"] == s) - cost["settings"][s]["mean_reply_prompt_tokens"]) < 0.01 for s in settings),
        "best/worst follow the stated rule": cost["best"] == cheapest_eligible and all(cost["settings"][s]["mean_probe_score"] >= top - 0.5 for s in cost["eligible_for_best"])
                                              and cost["worst"] == max(cost["settings"], key=lambda s: cost["settings"][s]["cost_10k_convos_all_calls_usd"]),
    }
    return all(steps.values()), json.dumps(steps)


def check_agent_md_instructions():
    text = (REPO_ROOT / "AGENT.md").read_text(encoding="utf-8")
    numbered = re.findall(r"^\d+\.\s", text, flags=re.M)
    cats = [c for c in ("Project description", "Technology stack", "Coding conventions", "Testing approach", "Prohibited actions") if c.lower() in text.lower()]
    return len(numbered) >= 5 and len(cats) >= 3, f"{len(numbered)} numbered instructions; categories present: {cats}"


def check_file_memory_triggers_and_commands():
    fm = file_memory_module()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    stamp = lambda hours: f"<!-- last-consolidated: {(now - timedelta(hours=hours)).isoformat()} -->"
    bullets = lambda n: "\n".join(f"- [2026-10-01] fact {i}" for i in range(n))
    steps = {
        "40 entries fresh -> not needed": not fm.consolidation_needed(f"{stamp(1)}\n{bullets(40)}\n", now)[0],
        "41 entries -> needed": fm.consolidation_needed(f"{stamp(1)}\n{bullets(41)}\n", now)[0],
        "25h-old timestamp -> needed": fm.consolidation_needed(f"{stamp(25)}\n{bullets(3)}\n", now)[0],
        "comment/blank lines not counted": len(fm.entry_lines("<!-- c -->\n\n- a\n<!--\nb\n-->\n")) == 1,
    }
    help_out = fm.chat_turn("/help")["output"]
    mem_out = fm.chat_turn("/memory")["output"]
    unk = fm.chat_turn("/nope")
    steps["/help lists the 4 commands"] = all(c in help_out for c in ("/memory", "/compact", "/dream", "/help"))
    steps["/memory shows AGENT.md and MEMORY.md"] = "AGENT.md" in mem_out and "MEMORY.md" in mem_out
    steps["unknown command reported"] = unk.get("unknown_command") is True
    system = fm.build_system_prompt(fm.load_agent(), fm.load_memory(str(REPO_ROOT / "MEMORY.md")))
    steps["system prompt contains AGENT.md and MEMORY.md text"] = "Never use eval()" in system and "Remembered facts" in system
    return all(steps.values()), json.dumps(steps)


def check_consolidation_and_dream_live():
    fm = file_memory_module()
    tmp = state["tmp"]
    path = tmp / "MEMORY_small.md"
    original = ("<!-- last-consolidated: 2026-10-15T09:00:00-07:00 -->\n# Project memory\n"
                "- [2026-10-01] The team captain is Maria.\n- [2026-10-05] Our captain is Maria.\n"
                "- [2026-10-03] Saturday league games start at 9am.\n- [2026-10-03] Saturday league games start at 10am.\n"
                "- [2026-10-02] The club mascot is a golden lion named Leo.\n- [2026-10-04] Parking is free on weekends behind the library.\n")
    path.write_text(original, encoding="utf-8")
    r = fm.consolidate(str(path))
    after = path.read_text(encoding="utf-8")
    steps = {
        "entry count dropped": r["after"] < r["before"],
        "duplicate captain lines merged to one": sum("captain" in l.lower() for l in after.splitlines() if l.startswith("- [20")) == 1,
        "same-date contradiction flagged unresolved with BOTH texts kept": "[unresolved" in after and "9am" in after and "10am" in after,
        "independent facts kept": "golden lion" in after and "Parking is free" in after,
        "backup of the original written": any(p.read_text(encoding="utf-8") == original for p in Path(os.environ["FILE_MEMORY_BACKUP_DIR"]).glob("MEMORY-*.md")),
        "timestamp refreshed with entry count": fm.read_consolidated_entries(after) == r["after"],
    }
    # /dream: mine a short conversation for a durable fact
    dpath = tmp / "MEMORY_dream.md"
    dpath.write_text("<!-- last-consolidated: 2026-10-15T09:00:00-07:00 -->\n# Project memory\n- [2026-10-01] The club mascot is a lion.\n", encoding="utf-8")
    d = fm.dream(str(dpath), [{"role": "user", "content": "I always run my team practice on Wednesdays at 6pm, please remember that."},
                              {"role": "assistant", "content": "Noted: practice is Wednesdays at 6pm."}])
    dtxt = dpath.read_text(encoding="utf-8")
    steps["/dream added a dated durable fact (not a duplicate)"] = len(d["added"]) >= 1 and re.search(r"wednesday|practice", dtxt, re.I) is not None \
        and dtxt.count("mascot") == 1 and all(a.startswith("[20") for a in d["added"])
    return all(steps.values()), json.dumps(steps) + f"; consolidate before/after entries = {r['before']}/{r['after']}"


def check_part4_artifacts():
    orig = (HW06 / "part4" / "MEMORY_original_55lines.md").read_text(encoding="utf-8")
    cons = (HW06 / "part4" / "MEMORY_consolidated.md").read_text(encoding="utf-8")
    res = json.loads((RAW / "part4_consolidation_result.json").read_text(encoding="utf-8"))
    gt = json.loads((HW06 / "part4" / "ground_truth.json").read_text(encoding="utf-8"))
    committed = git("ls-files", "reports/hw06/part4").splitlines()
    steps = {
        "original is 55 lines with >=3 duplicate groups and >=3 contradictions":
            len(orig.splitlines()) == 55 and len(gt["duplicate_groups"]) >= 3 and len(gt["conflicts"]) >= 3,
        "consolidated is under 40 lines": len(cons.splitlines()) < 40,
        "consolidated has an explicit Conflicts section": "## Conflicts" in cons,
        "no independent fact lost": res["unique_facts_lost"] == [],
        "both versions are committed in Git": "reports/hw06/part4/MEMORY_original_55lines.md" in committed and "reports/hw06/part4/MEMORY_consolidated.md" in committed,
    }
    return all(steps.values()), json.dumps(steps)


def check_generated_function_follows_agent_md():
    sys.path.insert(0, str(APP_DIR))
    sys.modules.setdefault("llm", type(sys)("llm"))          # verify_agent_md imports llm/file_memory for generation only
    sys.modules.setdefault("file_memory", type(sys)("file_memory"))
    sys.modules.setdefault("config", type(sys)("config"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("verify_agent_md_mod", APP_DIR / "verify_agent_md.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = json.loads((RAW / "part4_agent_md_verification.json").read_text(encoding="utf-8"))
    runs = rep["conditions"]["with_AGENT_md"]["runs"]
    recheck = [mod.check_rules(r["code"]).get("all_rules_followed") for r in runs]
    control = [mod.check_rules(r["code"]).get("all_rules_followed") for r in rep["conditions"]["control_no_AGENT_md"]["runs"]]
    steps = {"every stored AGENT.md-guided function passes an independent AST re-check": bool(runs) and all(recheck),
             "the generated code behaved correctly when executed": rep["conditions"]["with_AGENT_md"]["behaviour_correct"] == len(runs),
             "control (no AGENT.md) is worse": sum(bool(c) for c in control) < sum(bool(c) for c in recheck),
             "review mode answered with bullets only": rep["review_mode"]["only_bullets"]}
    return all(steps.values()), json.dumps(steps)


def cleanup():
    try:
        db = mongo_db()
        for c in ("messages", "summaries", "episodes", "usage_log"):
            db[c].delete_many({"user_id": TEMP_USER})
        db["fixtures"].delete_many({"fixture_name": "verify_hw06 temp fixture"})
    except Exception:
        pass
    tmp = state.get("tmp")
    if tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    commit = git("rev-parse", "HEAD") or "unknown"
    dirty = [l for l in git("status", "--porcelain").splitlines()
             if l.strip() and not l.strip().endswith("reports/hw06/verification.json")]
    proc, started = start_server_if_needed()
    old_seed = None
    try:
        if server_alive():
            try:                                   # model sampling uses VERIFY_SEED for this run
                old_seed = api("GET", "/api/settings").json().get("LLM_SEED")
                api("PUT", "/api/settings", json={"LLM_SEED": int(VERIFY_SEED)})
            except Exception:
                pass
        checks = [
            check("required_files_and_screenshots_present", check_required_files),
            check("mongodb_database_collections_and_validator", check_mongo_and_schema),
            check("backend_responds_on_port_base", check_backend_responds),
            check("fixtures_crud_roundtrip_persists_in_mongodb", check_fixture_crud_roundtrip),
            check("fixtures_validation_and_error_codes", check_fixture_validation),
            check("chat_returns_reply_and_writes_memory", check_chat_memory_pipeline),
            check("memory_and_aggregate_endpoints", check_memory_endpoints),
            check("read_only_chat_writes_nothing", check_read_only_chat_writes_nothing),
            check("chat_input_validation", check_chat_validation),
            check("part3_results_complete_and_consistent", check_part3_results),
            check("agent_md_has_five_instructions_in_three_categories", check_agent_md_instructions),
            check("file_memory_triggers_commands_and_prompt", check_file_memory_triggers_and_commands),
            check("consolidation_and_dream_work_on_temp_files", check_consolidation_and_dream_live),
            check("part4_artifacts_55_to_under_40_lines_committed", check_part4_artifacts),
            check("generated_function_follows_agent_md", check_generated_function_follows_agent_md),
        ]
    finally:
        if old_seed is not None:
            try:
                api("PUT", "/api/settings", json={"LLM_SEED": old_seed})
            except Exception:
                pass
        cleanup()
        stop_server(proc)

    report = {
        "homework": "HW6",
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
        "temp_chat_user": TEMP_USER,
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
