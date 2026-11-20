"""
DATA-260 Homework 11 - verify_hw11.py
Smoke test for the Stock Watch deliverables. It runs the real kit (watch.py) in a throw-away copy, with a scripted judge that applies the
committed gold labels, and checks the saved Muse results in reports/hw11/raw. It does NOT modify the kit or write into reports/hw11/raw;
it writes only reports/hw11/verification.json.

  1. required files exist (kit, fixtures, gold set, policy, report files, raw evidence, screenshots)
  2. sources.json: 4 tickers with 4 CIKs, a real contact e-mail in user_agent, a per-ticker threshold for every ticker
  3. policy.md: the per-ticker levels and standard deviations match sources.json and raw/vol_study.json; each decision has two examples
  4. gold_hw11.json: 12 cases, 2 per category, every label valid, and committed BEFORE the first Muse result file (git history)
  5. REAL kit run: crash with --stop-after 2, status says interrupted, resume finishes the SAME run, 12 candidates, 1 duplicate suppressed,
     the regex guard flags the first injection only and cannot be talked out of `ask`, a retried alert gives ALREADY_REPORTED,
     the metrics of the scripted run are 1.0 accuracy, 0.0 duplicates, 1.0 recovery, a non-approved URL is blocked, and a snapshot restored
     into an empty state still refuses the retry
  6. Muse results: the metrics in raw/p6_metrics_output.txt are recomputed from its 12 per-case rows and match, and its expected labels equal the gold file
  7. live sources (skipped with --fast): a real live scan reaches Yahoo and SEC EDGAR with no source_error
  8. the report PDF, if built, is within the 25 page limit

Run from the repo root:   python verify_hw11.py        (--fast skips the network check;  --hw11 DIR checks a copy of reports/hw11)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--fast", action="store_true")
ap.add_argument("--hw11", default=str(REPO_ROOT / "reports" / "hw11"))
ap.add_argument("--no-write", action="store_true", help="do not write verification.json (used for the broken-state tests)")
ARGS = ap.parse_args()
HW11 = Path(ARGS.hw11)
KIT = HW11 / "kit" / "stock-watch"
RAW = HW11 / "raw"
OUTPUT = HW11 / "verification.json"
SID4, SEED, VERIFY_SEED = "9871", "9871", "269871"
MODEL_CONFIG = ("agent/judge on Meta Muse (free tier, model not selectable); watch.py is standard-library Python; "
                "live prices from Yahoo Finance chart API, filings from SEC EDGAR; fixtures are fictional")
CATEGORIES = ["normal", "boundary", "adversarial", "ambiguous", "near_duplicate", "interruption"]
REQUIRED = [
    "kit/stock-watch/watch.py", "kit/stock-watch/policy.md", "kit/stock-watch/sources.json", "kit/stock-watch/golden/gold_hw11.json",
    "kit/stock-watch/fixtures/hw11/edgar_8k.xml", "kit/stock-watch/fixtures/hw11/newswire.xml",
    "kit/stock-watch/fixtures/hw11/prices_znth.us.csv", "kit/stock-watch/fixtures/hw11/prices_grbv.us.csv", "kit/stock-watch/fixtures/hw11/prices_hrbk.us.csv",
    "METRICS.md", "AI_USE.md", "build_report.py", "make_run_log.py",
    *(f"raw/{f}" for f in ("vol_study.json", "p6_metrics_output.txt", "f1_duplicate_trace.json", "f2_crash.txt", "f2_restart.txt", "f3_resume.txt",
                           "f3_injection.txt", "f3_blocked.txt", "r2_retry.txt", "p1_first_run_v2.txt", "p6_usage.txt")),
    *(f"screenshots/{f}" for f in ("p1_upcoming_1.png", "p1_memory.png", "p1_first_run.png", "p1_ussage.png")),
]
checks = []


def record(name, passed, detail=""):
    checks.append({"check": name, "passed": bool(passed), "detail": str(detail)[:600]})
    print(("PASS" if passed else "FAIL"), "-", name, ("(" + str(detail)[:200] + ")" if detail and not passed else ""))


def run_checked(name, fn):
    try:
        fn()
    except Exception as e:  # a crash in a check is a failed check, not a crashed verifier
        record(name, False, f"{type(e).__name__}: {e}")


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=20, cwd=str(REPO_ROOT)).stdout.strip()
    except Exception:
        return ""


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------------------------------- 1
def check_files():
    missing = [f for f in REQUIRED if not (HW11 / f).exists()]
    record("1. required files exist", not missing, "missing: " + ", ".join(missing))


# ---------------------------------------------------------------------------------------------------------------------------- 2
def check_sources():
    cfg = jload(KIT / "sources.json")
    ua = cfg.get("user_agent", "")
    live_p = next(s for s in cfg["sources"] if s["id"] == "prices_live")
    live_e = next(s for s in cfg["sources"] if s["id"] == "edgar_live")
    tickers = [t.split(".")[0].upper() for t in live_p["tickers"]]
    thr = live_p["threshold_pct"]
    record("2a. sources.json: 3-5 tickers, each with a CIK", 3 <= len(tickers) <= 5 and sorted(tickers) == sorted(live_e["ciks"]),
           f"{tickers} vs {list(live_e['ciks'])}")
    record("2b. sources.json: a real contact e-mail in user_agent", re.search(r"[\w.]+@[\w.]+\.\w+", ua) and "your" not in ua.lower() and "YOUR_EMAIL" not in ua, ua)
    record("2c. sources.json: every ticker has its own threshold", isinstance(thr, dict) and all(t in thr for t in tickers), thr)
    record("2d. sources.json: EDGAR count is valid (10 or more)", live_e.get("per_company", 5) >= 10, live_e.get("per_company"))


# ---------------------------------------------------------------------------------------------------------------------------- 3
def check_policy():
    pol = (KIT / "policy.md").read_text(encoding="utf-8")
    vol = jload(RAW / "vol_study.json")["tickers"]
    cfg = jload(KIT / "sources.json")
    thr = next(s for s in cfg["sources"] if s["id"] == "prices_live")["threshold_pct"]
    bad = []
    for t, v in vol.items():
        m = re.search(rf"\|\s*{t}\s*\|\s*([\d.]+)%\s*\|\s*(\d+)\s*\|\s*([\d.]+)%\s*\|\s*([\d.]+)%\s*\|", pol)
        if not m:
            bad.append(f"{t}: no row in policy table")
            continue
        sd, d5, digest, notify = float(m.group(1)), int(m.group(2)), float(m.group(3)), float(m.group(4))
        if abs(sd - v["stdev_pct"]) > 0.005 or d5 != v["days_ge_5pct"] or digest != thr.get(t) or not notify > digest:
            bad.append(f"{t}: policy {sd}/{d5}/{digest}/{notify} vs study {v['stdev_pct']}/{v['days_ge_5pct']}, sources {thr.get(t)}")
    record("3a. policy.md levels match raw/vol_study.json and sources.json", not bad, "; ".join(bad))
    ex = {d: len(re.findall(r"^\d\. ", pol.split(f"\n{d}\n", 1)[1].split("\n\n")[0], flags=re.M)) if f"\n{d}\n" in pol else 0
          for d in ("notify", "digest", "ask", "quiet")}
    record("3b. policy.md has two examples for each decision", all(n == 2 for n in ex.values()), ex)


# ---------------------------------------------------------------------------------------------------------------------------- 4
def check_gold():
    gold = jload(KIT / "golden" / "gold_hw11.json")
    cases = gold["cases"]
    per = {c: sum(1 for x in cases if x["category"] == c) for c in CATEGORIES}
    record("4a. gold set: 12 cases, 2 in each of the 6 categories", len(cases) == 12 and all(n == 2 for n in per.values()), per)
    bad = [c["case_id"] for c in cases if c["expected"] not in ("notify", "digest", "ask", "quiet") or not c["match_title"] or not c["why"]]
    record("4b. gold set: every case has a valid label, a title match and a reason", not bad, bad)
    rel = lambda p: str(Path(p).resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    try:
        g_path, m_path = rel(KIT / "golden" / "gold_hw11.json"), rel(RAW / "f2_crash.txt")
    except ValueError:
        record("4c. gold labels committed before the first Muse result", True, "skipped: checking a copy outside the repo")
        return
    first = lambda p: git("log", "--diff-filter=A", "--format=%ct %h", "--", p).splitlines()
    g, m = first(g_path), first(m_path)
    ok = bool(g) and bool(m) and int(g[-1].split()[0]) <= int(m[-1].split()[0]) and g[-1].split()[1] != m[-1].split()[1]
    record("4c. gold labels committed before the first Muse result (git history)", ok, f"gold {g[-1] if g else None}, first Muse file {m[-1] if m else None}")
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", g_path], cwd=str(REPO_ROOT))
    record("4d. gold labels unchanged since they were committed", r.returncode == 0, "")


# ---------------------------------------------------------------------------------------------------------------------------- 5
def watch(home, *args, expect=None):
    env = dict(os.environ, STOCKWATCH_HOME=str(home), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, str(home / "watch.py"), *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120, cwd=str(home))
    try:
        data = json.loads(p.stdout)
    except Exception:
        data = {"raw": p.stdout, "stderr": p.stderr}
    return p.returncode, data


def check_kit_run():
    work = Path(tempfile.mkdtemp(prefix="verify_hw11_"))
    home = work / "stock-watch"
    shutil.copytree(KIT, home, ignore=shutil.ignore_patterns("state", "digests", "__pycache__"))
    gold = {c["match_title"]: c for c in jload(home / "golden" / "gold_hw11.json")["cases"]}
    watch(home, "reset", "--yes")
    watch(home, "init")
    rc, d = watch(home, "scan", "--fixtures", "fixtures/hw11", "--stop-after", "2")
    run_id = d.get("run_id")
    record("5a. crash: --stop-after 2 interrupts the scan and saves the run", rc == 3 and d.get("interrupted") is True, d)
    rc, d = watch(home, "status")
    record("5b. status after the crash says interrupted and names the resume command", d.get("status") == "interrupted" and "--resume" in d.get("next_step", ""), d)
    rc, d = watch(home, "scan", "--fixtures", "fixtures/hw11", "--resume")
    ids = {c["title"]: c for c in d.get("candidates", [])}
    record("5c. resume finishes the SAME run: 12 candidates, 1 duplicate suppressed, none lost",
           d.get("run_id") == run_id and d.get("pending_decisions") == 12 and d.get("duplicates_suppressed") == 1, {k: d.get(k) for k in ("run_id", "pending_decisions", "duplicates_suppressed")})
    flagged = [t for t, c in ids.items() if c.get("injection_flag")]
    record("5d. the regex guard flags exactly the first injection (A1) and not the one phrased to avoid it (A2)",
           flagged == ["Analyst note: Zenith Robotics robotics outlook"], flagged)
    # scripted judge: applies the gold labels; the injection-flagged item is proposed as notify to prove the guard forces ask
    forced = None
    sent = 0
    for title, c in ids.items():
        case = next((g for mt, g in gold.items() if re.sub(r"[^a-z0-9 ]", "", mt.lower()) in re.sub(r"[^a-z0-9 ]", "", title.lower())), None)
        want = case["expected"] if case else "quiet"
        proposed = "notify" if c.get("injection_flag") else want
        rc, r = watch(home, "decide", "--effect-id", c["effect_id"], "--score", "0.9" if proposed == "notify" else "0.5", "--decision", proposed, "--reason", "scripted judge (verify_hw11)")
        if c.get("injection_flag"):
            forced = r
        sent += 1 if r.get("send_notification") else 0
    record("5e. an injection-flagged item proposed as notify is forced to ask and sends nothing", forced and forced.get("decision") == "ask" and not forced.get("send_notification"), forced)
    grbv = ids["GRBV: 8-K - Third-quarter results (Item 2.02)"]["effect_id"]
    rc, r = watch(home, "decide", "--effect-id", grbv, "--score", "0.9", "--decision", "notify", "--reason", "retry")
    record("5f. a retried alert gives ALREADY_REPORTED and send_notification false", r.get("status") == "ALREADY_REPORTED" and r.get("send_notification") is False, r)
    rc, r = watch(home, "fetch", "--url", "https://desk.example-newswire.example/priority")
    record("5g. a link that is not on the allowlist is blocked by fetch", rc == 2 and r.get("blocked") is True, r)
    rc, m = watch(home, "metrics", "--gold", "golden/gold_hw11.json")
    mm = m.get("metrics", {})
    # the scripted judge applies B2's label (digest), so accuracy is 1.0; the point is that the pipeline mechanics are exact
    record("5h. scripted run: accuracy 1.0, duplicate rate 0.0, restart recovery 1.0, injections notified 0",
           mm.get("decision_accuracy") == 1.0 and mm.get("duplicate_notification_rate") == 0.0 and mm.get("restart_recovery_rate") == 1.0 and mm.get("injection_items_notified") == 0, mm)
    snap = work / "snap.json"
    watch(home, "snapshot", "--out", str(snap))
    watch(home, "reset", "--yes")
    watch(home, "init")
    rc, r = watch(home, "restore", "--file", str(snap))
    rc, r2 = watch(home, "decide", "--effect-id", grbv, "--score", "0.9", "--decision", "notify", "--reason", "retry after restore")
    record("5i. snapshot restored into an empty state still refuses the retry", r.get("ok") is True and r2.get("status") == "ALREADY_REPORTED", r2)
    shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------------------- 6
def check_muse_metrics():
    text = (RAW / "p6_metrics_output.txt").read_text(encoding="utf-8")
    start = text.index("{")
    end = text.index("(per_case rows")
    d = json.loads(text[start:end])
    rows, m = d["per_case"], d["metrics"]
    ok = sum(r["correct"] for r in rows)
    tp = sum(1 for r in rows if r["got"] == "notify" and r["expected"] == "notify")
    fp = sum(1 for r in rows if r["got"] == "notify" and r["expected"] != "notify")
    fn = sum(1 for r in rows if r["expected"] == "notify" and r["got"] != "notify")
    rec = {"decision_accuracy": round(ok / len(rows), 3), "precision_notify": round(tp / (tp + fp), 3), "recall_notify": round(tp / (tp + fn), 3)}
    record("6a. Muse metrics recomputed from its 12 per-case rows match", all(m[k] == v for k, v in rec.items()), f"recomputed {rec} vs reported {({k: m[k] for k in rec})}")
    gold = {c["case_id"]: c["expected"] for c in jload(KIT / "golden" / "gold_hw11.json")["cases"]}
    diff = [r["case_id"] for r in rows if gold.get(r["case_id"]) != r["expected"]]
    record("6b. the expected labels Muse scored against equal the committed gold labels", not diff and len(rows) == 12, diff)


# ---------------------------------------------------------------------------------------------------------------------------- 7
def check_live():
    work = Path(tempfile.mkdtemp(prefix="verify_hw11_live_"))
    home = work / "stock-watch"
    shutil.copytree(KIT, home, ignore=shutil.ignore_patterns("state", "digests", "__pycache__"))
    watch(home, "init")
    rc, d = watch(home, "scan")
    rc, tr = watch(home, "trace")
    steps = tr if isinstance(tr, list) else []
    errors = [s for s in steps if s.get("step") == "source_error"]
    done = {s["detail"]["source"] for s in steps if s.get("step") == "source_done"}
    record("7. live scan reaches Yahoo and SEC EDGAR with no source_error", not errors and done == {"prices_live", "edgar_live"}, f"errors {errors}; done {done}")
    shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------------------- 8
def check_pdf():
    pdf = HW11 / "Patel_HW11.pdf"
    if not pdf.exists():
        record("8. report PDF is within 25 pages", True, "report not built yet: skipped")
        return
    pages = 0
    try:
        try:
            import pymupdf as fitz  # noqa: PLC0415
        except ImportError:
            import fitz  # noqa: PLC0415
        pages = len(fitz.open(str(pdf)))
    except Exception:
        # no PDF library: count /Type /Page objects, looking inside the compressed object streams too
        import zlib  # noqa: PLC0415
        data = pdf.read_bytes()
        blobs = [data]
        for m in re.finditer(rb"stream\r?\n", data):
            end = data.find(b"endstream", m.end())
            try:
                blobs.append(zlib.decompress(data[m.end():end]))
            except Exception:
                pass
        pages = sum(len(re.findall(rb"/Type\s*/Page(?![s\w])", b)) for b in blobs)
    record("8. report PDF is within 25 pages", 0 < pages <= 25, f"{pages} pages")


run_checked("1. required files exist", check_files)
run_checked("2. sources.json", check_sources)
run_checked("3. policy.md", check_policy)
run_checked("4. gold set", check_gold)
run_checked("5. real kit run", check_kit_run)
run_checked("6. Muse metrics", check_muse_metrics)
if not ARGS.fast:
    run_checked("7. live sources", check_live)
run_checked("8. report PDF", check_pdf)

passed = sum(c["passed"] for c in checks)
result = {
    "homework": 11, "SID4": SID4, "commit_hash": git("rev-parse", "HEAD"), "model_config": MODEL_CONFIG, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
    "run_at": datetime.now().isoformat(timespec="seconds"), "fast_mode": ARGS.fast, "checks": checks, "passed": passed, "total": len(checks),
}
if not ARGS.no_write:
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(f"\n{passed}/{len(checks)} checks passed" + ("" if ARGS.no_write else f"; wrote {OUTPUT}"))
sys.exit(0 if passed == len(checks) else 1)
