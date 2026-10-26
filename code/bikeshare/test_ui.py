"""
DATA-260 Homework 7 - Part 4: real end-to-end test of the server and the page (real HTTP, real headless Chromium, real model).

    python code/bikeshare/test_ui.py                       # API failure paths + one full UI run (membership scenario)
    python code/bikeshare/test_ui.py --both --shots DIR    # both acceptance scenarios, saving a full-page PNG of each result

The server is started on port 8872 if nothing is listening there, and stopped afterwards.
"""

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8872"
DATA = HERE / "data"
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"   ({extra})" if extra and not cond else ""), flush=True)


def port_open():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", 8872)) == 0


def start_server():
    if port_open():
        return None
    proc = subprocess.Popen([sys.executable, str(HERE / "server.py")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if port_open():
            return proc
        time.sleep(0.5)
    raise RuntimeError("server did not start")


GOOD_HEADER = "ride_id,rideable_type,started_at,ended_at,member_casual\n"


def post(files=None, url="https://www.lyft.com/bikes/bay-wheels/pricing"):
    return httpx.post(f"{BASE}/api/run", files=files, data={"pricing_url": url}, timeout=30)


def api_failure_paths():
    print("\n### upload validation (no model involved)")
    r = post({"csv": ("trips.txt", b"a,b\n1,2\n", "text/plain")})
    check("a non-.csv file is refused with 400", r.status_code == 400 and ".csv" in r.json()["detail"], r.text)
    r = post({"csv": ("trips.csv", b"a,b\n1,2\n", "text/csv")})
    check("a CSV without the required columns is refused and the message names them", r.status_code == 400 and "started_at" in r.json()["detail"], r.text)
    r = post({"csv": ("trips.csv", GOOD_HEADER.encode(), "text/csv")})
    check("a CSV with a header but no rows is refused", r.status_code == 400 and "no trip rows" in r.json()["detail"], r.text)
    r = post({"csv": ("trips.csv", b"\xff\xfe\x00bad", "text/csv")})
    check("a binary file named .csv is refused as unreadable, not a 500", r.status_code == 400, f"{r.status_code} {r.text[:100]}")
    row = GOOD_HEADER.encode() + b"1,classic_bike,2024-01-01 08:00:00,2024-01-01 08:10:00,casual\n"
    r = post({"csv": ("trips.csv", row, "text/csv")}, url="http://www.lyft.com/bikes/bay-wheels/pricing")
    check("an http:// pricing URL is refused", r.status_code == 400 and "https" in r.json()["detail"], r.text)
    r = post({"csv": ("trips.csv", row, "text/csv")}, url="")
    check("an empty pricing URL is refused", r.status_code in (400, 422), r.text)
    r = httpx.post(f"{BASE}/api/run", data={"pricing_url": "https://x.test/p"}, timeout=30)
    check("no file at all is refused (422)", r.status_code == 422)
    big = GOOD_HEADER.encode() + (b"1,classic_bike,2024-01-01 08:00:00,2024-01-01 08:10:00,casual\n" * 90000)
    r = post({"csv": ("big.csv", big, "text/csv")})
    check("a file over 5 MB is refused with 413", r.status_code == 413, f"{r.status_code} {len(big)}")
    check("an unknown run id is a 404", httpx.get(f"{BASE}/api/runs/nope", timeout=10).status_code == 404)
    check("the page itself is served", "Bay Wheels" in httpx.get(BASE + "/", timeout=10).text)


def ui_run(pw, scenario: str, shots: Path | None, expect_busy_check: bool):
    csv_path = DATA / f"scenario_{scenario}.csv"
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    page.on("pageerror", lambda e: print(f"    [{scenario}] BROWSER ERROR: {e}", flush=True))
    page.on("response", lambda r: print(f"    [{scenario}] API {r.status} {r.url[-30:]}", flush=True) if "/api/" in r.url and r.status != 200 else None)
    page.goto(BASE + "/")
    check(f"[{scenario}] the page shows one CSV field, one URL field and a Run button",
          page.locator("input[type=file]").count() == 1 and page.locator("input[type=url]").count() == 1 and page.locator("#run").count() == 1)
    check(f"[{scenario}] the URL field is pre-filled with the Bay Wheels pricing page", "lyft.com/bikes/bay-wheels/pricing" in page.input_value("#url"))
    page.set_input_files("#csv", str(csv_path))
    page.click("#run")
    page.wait_for_selector(".ev.tool_call", timeout=120000)
    check(f"[{scenario}] a tool call appears in the timeline while the run is still going", page.locator("#run").is_disabled())
    if expect_busy_check:
        r = post({"csv": ("trips.csv", csv_path.read_bytes(), "text/csv")})
        check(f"[{scenario}] a second run while one is active is refused with 409", r.status_code == 409, f"{r.status_code} {r.text[:100]}")
    page.wait_for_selector(".banner", timeout=420000)
    box = page.locator("#results")
    text = box.inner_text()
    check(f"[{scenario}] the timeline shows tool calls and observations", page.locator(".ev.tool_call").count() >= 3 and page.locator(".ev.observation").count() >= 3)
    check(f"[{scenario}] the timeline names all three tools", all(t in page.locator("#timeline").inner_text() for t in ("csv_sql", "policy_retriever", "calculator")))
    check(f"[{scenario}] the results panel shows the decision banner", page.locator(".banner").inner_text().split("\n")[0] in ("Buy Monthly Membership", "Pay Per Ride/Minute"))
    check(f"[{scenario}] the metrics strip shows steps, total time and stop reason", all(k in text for k in ("Steps", "Total time", "Stop reason")) and "final_answer" in text)
    check(f"[{scenario}] the cost comparison table is shown", "Pay per ride/minute" in text and "Monthly membership" in text and "Residual charges" in text)
    check(f"[{scenario}] the weekly table is shown", page.locator("#results table").count() >= 2)
    check(f"[{scenario}] citations show the pricing URL, a capture time and a 64-hex SHA-256",
          "lyft.com/bikes/bay-wheels/pricing" in text and "Captured: 20" in text and len(next(ln for ln in text.split("\n") if "SHA-256" in ln).split(": ")[-1].strip()) == 64)
    check(f"[{scenario}] the independent check is displayed", "Independent check" in text)
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
        # the timeline panel scrolls on screen; expand it (layout only) so the capture shows every step, and cap nothing
        page.add_style_tag(content="#timeline{max-height:none !important} pre{max-height:none !important}")
        page.screenshot(path=str(shots / f"part4_ui_{scenario}.png"), full_page=True)
    verdict = "MATCHES" if "match the recomputation" in text else "MISMATCH"
    print(f"    [{scenario}] decision={page.locator('.banner').inner_text().splitlines()[0]!r}; independent check: {verdict}", flush=True)
    browser.close()


def xss_check(pw):
    print("\n### the page renders model output as text, never as HTML")
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.goto(BASE + "/")
    evil = '<img src=x onerror="window.pwned=1"><script>window.pwned=2</script>'
    fake = {"steps": 1, "total_time_s": 1, "stop_reason": "final_answer", "tool_calls": {"calls": 1, "failed": 0}, "tokens": {"input": 1, "output": 1},
            "result": {"decision": "Pay Per Ride/Minute", "justification": evil, "costs": {"pay_per_use_total": 1, "membership_fee_total": 2, "membership_residual_charges": 0,
                                                                                              "membership_total": 2, "months": 1},
                       "break_even": {"rides_per_month": 1, "actual_rides_per_month": 1}, "weekly": [{"week": evil, "rides": 1, "avg_duration_min": 1, "spend": 1}],
                       "assumptions": [evil], "citations": []},
            "citations": [{"quote": evil, "found_in_snapshot": False}], "snapshot": None, "verification": {"checked": False}}
    page.evaluate("(run) => renderResults(run)", fake)
    page.evaluate("(ev) => addEvent(ev)", {"step": 1, "kind": "observation", "tool": "csv_sql", "success": True, "output": evil, "t_ms": 5})
    check("HTML in the justification, weekly table, assumptions, citations and observations is shown as text, not executed",
          page.evaluate("window.pwned") is None and page.locator("#results img, #timeline img, #results script").count() == 0 and evil in page.locator("#results").inner_text())
    browser.close()


def polling_resilience(pw):
    """The server is mocked at the network layer, so this needs no model: a few failed polls must not freeze the page, and a server that
    stays unreachable must produce a visible error and give the Run button back."""
    print("\n### polling survives failed requests (mocked network)")
    done = {"status": "done", "events": [{"step": 1, "kind": "tool_call", "tool": "csv_sql", "input": {"sql": "SELECT 1"}, "t_ms": 5}],
            "result": {"stop_reason": "final_answer", "steps": 1, "total_time_s": 1, "tool_calls": {"calls": 1, "failed": 0}, "tokens": {"input": 1, "output": 1},
                       "result": {"decision": "Pay Per Ride/Minute", "justification": "x" * 50,
                                  "costs": {"pay_per_use_total": 1, "membership_fee_total": 2, "membership_residual_charges": 0, "membership_total": 2, "months": 1},
                                  "break_even": {"rides_per_month": 1, "actual_rides_per_month": 1}, "weekly": [], "assumptions": [], "citations": []},
                       "citations": [], "snapshot": None, "verification": {"checked": False}}}
    for label, fail_first, expect_banner in (("3 failed polls then success", 3, True), ("server unreachable for good", 10**6, False)):
        browser = pw.chromium.launch()
        page = browser.new_page()
        seen = {"n": 0}

        def make_route(limit, counter):
            def runs_route(route, _request=None):
                counter["n"] += 1
                if counter["n"] <= limit:
                    route.abort()
                else:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(done))
            return runs_route

        page.route("**/api/run", lambda route, _request=None: route.fulfill(status=200, content_type="application/json", body=json.dumps({"run_id": "x", "rows": 5})))
        page.route("**/api/runs/x", make_route(fail_first, seen))
        page.goto(BASE + "/")
        page.set_input_files("#csv", {"name": "t.csv", "mimeType": "text/csv", "buffer": b"a\n1\n"})
        page.click("#run")
        if expect_banner:
            page.wait_for_selector(".banner", timeout=30000)
            check(f"[{label}] the page recovers and shows the result", page.locator(".banner").count() == 1 and seen["n"] == 4, str(seen))
        else:
            page.wait_for_function("document.getElementById('msg').textContent.includes('Lost contact')", timeout=40000)
            check(f"[{label}] the page says it lost contact and re-enables Run", page.locator("#run").is_enabled() and "Lost contact" in page.inner_text("#msg"))
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--both", action="store_true")
    ap.add_argument("--only", choices=["membership_wins", "payperuse_wins"], help="run just this scenario in the UI")
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--skip-run", action="store_true", help="API/XSS checks only (no model run)")
    args = ap.parse_args()
    server = start_server()
    try:
        api_failure_paths()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            xss_check(pw)
            polling_resilience(pw)
            if not args.skip_run:
                print("\n### full UI run(s) with the real model")
                scenarios = [args.only] if args.only else ["membership_wins", "payperuse_wins"] if args.both else ["membership_wins"]
                for n, sc in enumerate(scenarios):
                    ui_run(pw, sc, args.shots, expect_busy_check=(n == 0))
    finally:
        if server:
            server.terminate()
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for n in failed:
        print("FAILED:", n)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
