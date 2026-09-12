"""
DATA-260 Homework 2 - verify_hw02.py
A self-check smoke test confirming the HW2 system runs and passes a few
basic checks. Writes results to reports/hw02/verification.json.

This does NOT modify any application code - it only starts a temporary
FastAPI server subprocess (killed at the end) and runs the LangGraph
pipeline directly.

Run with: python verify_hw02.py   (from the code/ folder, inside the venv)
"""

import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
VERIFICATION_OUTPUT = REPO_ROOT / "reports" / "hw02" / "verification.json"

SID4 = "9871"
SEED = "9871"
VERIFY_SEED = "269871"
PORT_BASE = 8871
MODEL_CONFIG = "qwen3:8b (Ollama, temperature=0.7)"


def get_commit_hash():
    try:
        result = subprocess.run(
            "git rev-parse HEAD", capture_output=True, text=True,
            timeout=10, shell=True, cwd=str(REPO_ROOT),
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def check(name, fn):
    try:
        passed, detail = fn()
        return {"check": name, "passed": passed, "detail": detail}
    except Exception as e:
        return {"check": name, "passed": False, "detail": f"Exception: {e}"}


def check_required_files():
    required = [
        THIS_DIR / "web_application" / "static" / "style.css",
        THIS_DIR / "web_application" / "static" / "app.js",
        THIS_DIR / "web_application" / "templates" / "index.html",
        THIS_DIR / "web_application" / "main.py",
        THIS_DIR / "agent_graph.py",
        THIS_DIR / "loop_safety_experiments.py",
        REPO_ROOT / "reports" / "hw02" / "cases" / "schema_input.json",
        REPO_ROOT / "reports" / "hw02" / "cases" / "adversarial_input.json",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
    if missing:
        return False, f"Missing files: {missing}"
    return True, f"All {len(required)} required files present."


def check_fastapi_responds():
    """Actually starts the FastAPI app as a subprocess and confirms it
    responds on PORT_BASE, then shuts it down."""
    main_py = THIS_DIR / "web_application" / "main.py"
    proc = subprocess.Popen(
        [sys.executable, str(main_py)],
        cwd=str(THIS_DIR / "web_application"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        # Give the server a few seconds to start up
        deadline = time.time() + 10
        last_error = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://localhost:{PORT_BASE}/", timeout=2) as resp:
                    if resp.status == 200:
                        return True, f"FastAPI responded 200 OK on port {PORT_BASE}."
            except Exception as e:
                last_error = e
                time.sleep(1)
        return False, f"FastAPI did not respond on port {PORT_BASE} within 10s: {last_error}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_langgraph_finishes():
    """Runs the actual LangGraph pipeline with a wall-clock timeout to
    confirm it terminates rather than hanging. Uses turn_ceiling=2 (which
    we've verified structurally forces an early END after Planner's
    first attempt) to keep this check fast."""
    sys.path.insert(0, str(THIS_DIR))
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import agent_graph
    from model_client import ModelClient

    def run_it():
        graph = agent_graph.build_graph()
        llm = ModelClient(model="qwen3:8b", temperature=0.0)
        initial_state = {
            "title": "Verification smoke test",
            "content": "A short fixture used only to verify the graph terminates.",
            "email": "verify@example.com",
            "strict": False,
            "task": "verify",
            "llm": llm,
            "planner_proposal": {},
            "reviewer_feedback": {},
            "turn_count": 0,
            "turn_ceiling": 2,
            "schema_error": "",
        }
        final_state = dict(initial_state)
        for step in graph.stream(initial_state):
            for _, updates in step.items():
                final_state.update(updates)
        return final_state

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_it)
        try:
            final_state = future.result(timeout=120)
        except FutureTimeoutError:
            return False, "LangGraph pipeline did not finish within 120s - possible hang."

    return True, (
        f"LangGraph pipeline finished with turn_count={final_state.get('turn_count')} "
        f"(did not hang)."
    )


def main():
    checks = [
        check("required_files_present", check_required_files),
        check("fastapi_responds_on_port_base", check_fastapi_responds),
        check("langgraph_finishes_without_hanging", check_langgraph_finishes),
    ]

    all_passed = all(c["passed"] for c in checks)

    report = {
        "homework": "HW2",
        "sid4": SID4,
        "commit_hash": get_commit_hash(),
        "model_config": MODEL_CONFIG,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "all_checks_passed": all_passed,
        "checks": checks,
    }

    VERIFICATION_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(VERIFICATION_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nWritten to: {VERIFICATION_OUTPUT}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()