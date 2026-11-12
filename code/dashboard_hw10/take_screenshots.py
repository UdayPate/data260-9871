"""
DATA-260 Homework 10 Part 1 - real screenshots of the running dashboard (headless Chromium driven by Playwright; a real Streamlit server, real clicks and typing).

    code\\venv\\Scripts\\python.exe code/dashboard_hw10/take_screenshots.py

Starts the dashboard on port 8873, opens each page, and saves reports/hw10/screenshots/:
  fig1_summary.png, fig2_evaluation.png, fig3_trace_cache_miss_<id8>.png, fig4_trace_cache_hit_<id8>.png, fig5_trace_failed_<id8>.png
The three trace screenshots are taken by typing the trace_id into the page's input box. The page name and trace_id are in each file name and are printed in the report caption.
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "reports" / "hw10" / "screenshots"
PORT = 8873
URL = f"http://localhost:{PORT}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ids = json.loads((ROOT / "reports" / "hw10" / "raw" / "part4_trace_ids.json").read_text(encoding="utf-8"))
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(HERE / "app.py"), "--server.port", str(PORT), "--server.headless", "true",
                               "--browser.gatherUsageStats", "false"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(f"{URL}/_stcore/health", timeout=2).read() == b"ok":
                    break
            except OSError:
                time.sleep(1)
        else:
            print("dashboard did not start", file=sys.stderr)
            return 1
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1700, "height": 1950})
            page.goto(URL)
            page.get_by_text("Semantic-cache hit rate").first.wait_for(timeout=30000)
            time.sleep(1.5)
            page.screenshot(path=str(OUT / "fig1_summary.png"), full_page=True)
            page.set_viewport_size({"width": 1700, "height": 2150})  # Streamlit scrolls inside the page, so make the window tall enough to show the whole page
            page.get_by_text("Evaluation", exact=True).first.click()
            page.get_by_text("Part 3 - is the judge reliable?").wait_for(timeout=30000)
            time.sleep(2)
            page.screenshot(path=str(OUT / "fig2_evaluation.png"), full_page=True)
            page.set_viewport_size({"width": 1700, "height": 1500})
            page.get_by_text("Trace lookup", exact=True).first.click()
            box = page.get_by_placeholder("paste a trace_id")
            box.wait_for(timeout=30000)
            for fig, key, kind in ((3, "cache_miss_success", "cache_miss"), (4, "cache_hit", "cache_hit"), (5, "failed", "failed")):
                tid = ids[key]["trace_id"]
                box.fill(tid)
                box.press("Enter")
                page.get_by_text(tid).first.wait_for(timeout=30000)
                time.sleep(2)
                path = OUT / f"fig{fig}_trace_{kind}_{tid[:8]}.png"
                page.screenshot(path=str(path), full_page=True)
                print("saved", path.name, "for trace", tid)
            browser.close()
        print("saved fig1_summary.png, fig2_evaluation.png")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
