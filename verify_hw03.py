import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VERIFICATION_OUTPUT = REPO_ROOT / "reports" / "hw03" / "verification.json"

SID4 = "9871"
SEED = "9871"
VERIFY_SEED = "269871"
PORT_BASE = 8871
MODEL_CONFIG = "sentence-transformers/all-MiniLM-L6-v2 (embeddings); qwen3:8b (Ollama, Parts 1-2 agent work)"


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
        REPO_ROOT / "code" / "web_application" / "auth.py",
        REPO_ROOT / "code" / "web_application" / "templates" / "base.html",
        REPO_ROOT / "code" / "web_application" / "templates" / "login.html",
        REPO_ROOT / "code" / "web_application" / "templates" / "dashboard.html",
        REPO_ROOT / "rag_chunking_comparison.py",
        REPO_ROOT / "summarize_chunking_comparison.py",
        REPO_ROOT / "reports" / "hw03" / "questions.yaml",
        REPO_ROOT / "reports" / "hw03" / "SOURCES.md",
        REPO_ROOT / "reports" / "hw03" / "CORPUS_MANIFEST.json",
        REPO_ROOT / "reports" / "hw03" / "METRICS.md",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
    if missing:
        return False, f"Missing files: {missing}"
    return True, f"All {len(required)} required files present."


def check_fastapi_auth_responds():
    """Starts the FastAPI app as a subprocess and confirms both '/' and
    '/dashboard' behave correctly: home responds 200, and dashboard
    (unauthenticated) correctly redirects to /login rather than granting
    access - a real functional check of Part 1's protection, not just
    'does the server start'."""
    main_py = REPO_ROOT / "code" / "web_application" / "main.py"
    proc = subprocess.Popen(
        [sys.executable, str(main_py)],
        cwd=str(REPO_ROOT / "code" / "web_application"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 10
        last_error = None
        home_ok = False
        while time.time() < deadline and not home_ok:
            try:
                with urllib.request.urlopen(f"http://localhost:{PORT_BASE}/", timeout=2) as resp:
                    home_ok = resp.status == 200
            except Exception as e:
                last_error = e
                time.sleep(1)

        if not home_ok:
            return False, f"Home page did not respond on port {PORT_BASE}: {last_error}"

        # Dashboard, unauthenticated, must NOT grant access - it should
        # redirect to /login. urllib follows redirects by default and
        # will land on /login's 200, so we check the final URL instead.
        req = urllib.request.urlopen(f"http://localhost:{PORT_BASE}/dashboard", timeout=5)
        final_url = req.geturl()
        if final_url.endswith("/login"):
            return True, (
                f"Home responded 200 OK, and unauthenticated /dashboard "
                f"correctly redirected to /login (protection enforced)."
            )
        return False, f"/dashboard did not redirect to /login (landed on {final_url})"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_corpus_size_and_integrity():
    """Reads CORPUS_MANIFEST.json and verifies: (1) the recorded total
    meets the 200KB requirement, and (2) each file's recorded SHA-256
    hash actually matches the current file on disk (real integrity
    check, not just 'does the manifest exist')."""
    manifest_path = REPO_ROOT / "reports" / "hw03" / "CORPUS_MANIFEST.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    total_bytes = manifest.get("total_corpus_bytes", 0)
    if total_bytes < 200_000:
        return False, f"Corpus is only {total_bytes} bytes; must be >= 200,000."

    mismatches = []
    for doc in manifest.get("documents", []):
        file_path = REPO_ROOT / doc["filename"]
        if not file_path.exists():
            mismatches.append(f"{doc['filename']} - file missing")
            continue
        actual_hash = sha256_of_file(file_path)
        if actual_hash != doc["sha256"]:
            mismatches.append(f"{doc['filename']} - hash mismatch")

    if mismatches:
        return False, f"Corpus size OK ({total_bytes} bytes) but integrity issues: {mismatches}"

    return True, (
        f"Corpus totals {total_bytes} bytes (>= 200KB requirement met), "
        f"and all {len(manifest.get('documents', []))} file hashes match "
        f"CORPUS_MANIFEST.json."
    )


def main():
    checks = [
        check("required_files_present", check_required_files),
        check("fastapi_auth_home_and_protection", check_fastapi_auth_responds),
        check("corpus_size_and_hash_integrity", check_corpus_size_and_integrity),
    ]

    all_passed = all(c["passed"] for c in checks)

    report = {
        "homework": "HW3",
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