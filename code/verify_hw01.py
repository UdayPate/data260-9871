"""
DATA-260 Homework 1 - verify_hw01.py
A self-check script confirming the HW1 system runs and passes a few basic
checks. Writes its results to reports/hw01/verification.json.

Run with: python verify_hw01.py   (from the code/ folder, inside the venv)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
VERIFICATION_OUTPUT = REPO_ROOT / "reports" / "hw01" / "verification.json"


def check(name, fn):
    """Run a single check function, catching any exception as a failure."""
    try:
        passed, detail = fn()
        return {"check": name, "passed": passed, "detail": detail}
    except Exception as e:
        return {"check": name, "passed": False, "detail": f"Exception: {e}"}


def check_required_files():
    required = [
        REPO_ROOT / "DOMAIN_SCHEMA.md",
        REPO_ROOT / "AGENT.md",
        REPO_ROOT / "src" / "model_client.py",
        REPO_ROOT / "code" / "agents_demo.py",
        REPO_ROOT / "code" / "hw1_client.py",
        REPO_ROOT / "code" / "Dockerfile",
        REPO_ROOT / "code" / "web_application" / "index.html",
        REPO_ROOT / "code" / "web_application" / "app.js",
        REPO_ROOT / "reports" / "hw01" / "cases" / "nondeterminism_input.json",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
    if missing:
        return False, f"Missing files: {missing}"
    return True, f"All {len(required)} required files present."


def check_agent_pipeline_runs():
    # Import here so a missing dependency doesn't crash the whole script
    sys.path.insert(0, str(THIS_DIR))
    from agents_demo import run_planner, run_reviewer, finalize

    title = "Verification Test Fixture"
    content = (
        "This is a short test fixture used only to verify that the "
        "Planner, Reviewer, and Finalizer pipeline runs end to end and "
        "produces valid JSON with exactly three tags and a summary."
    )

    planner_raw = run_planner(title, content)
    reviewer_raw = run_reviewer(planner_raw, title, content)
    result = finalize(reviewer_raw)

    if "tags" not in result or "summary" not in result:
        return False, f"Finalized output missing expected keys: {result}"
    if len(result["tags"]) != 3:
        return False, f"Expected exactly 3 tags, got {len(result['tags'])}: {result['tags']}"

    return True, f"Pipeline produced valid output: {json.dumps(result)}"


def check_model_client_importable():
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from model_client import ModelClient  # noqa: F401
    return True, "src/model_client.py imports successfully and exposes ModelClient."


def main():
    checks = [
        check("required_files_present", check_required_files),
        check("model_client_importable", check_model_client_importable),
        check("agent_pipeline_runs_end_to_end", check_agent_pipeline_runs),
    ]

    all_passed = all(c["passed"] for c in checks)

    report = {
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