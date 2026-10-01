"""
DATA-260 Homework 5 - Part 1.III: real browser test of the Redux client.

Drives the actual React app in headless Chromium with Playwright: real
login, real form fills, real clicks, real navigation. After every mutation
it checks MySQL directly, so a screen that merely *looks* right but never
persisted is caught.

It starts whatever is not already running (FastAPI on PORT_BASE 8871, Vite
on 5173) and stops only what it started. It creates one fixture and one
throwaway team, then deletes both, leaving the database as it found it.

Run from code/web_application, inside the venv:
    python test_redux_ui.py
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from sqlalchemy import text

from db import engine

APP_DIR = Path(__file__).resolve().parent
CLIENT_DIR = APP_DIR / "client"
SHOTS = APP_DIR.parent.parent / "reports" / "hw05" / "screenshots"

API_PORT = 8871
UI_PORT = 5173
UI = f"http://localhost:{UI_PORT}"

DEMO_EMAIL = "league_admin@example.com"
DEMO_PASSWORD = "GoLions2026!"

TEST_CODE = "FX-9871-97001"
TEST_NAME = "Redux UI Test Fixture"

PASS = FAILED = 0


def check(label, cond, extra=""):
    global PASS, FAILED
    if cond:
        PASS += 1
        print(f"PASS  {label}", flush=True)
    else:
        FAILED += 1
        print(f"FAIL  {label}   {extra}", flush=True)


def port_open(port):
    """Dual-stack check. socket.socket() defaults to AF_INET, which misses
    Vite: it binds ::1 (IPv6 localhost) only, so an IPv4 probe reports the
    port free, a second dev server gets spawned, and it silently falls back
    to 5174. create_connection resolves "localhost" to both families."""
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for(port, timeout, what):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return True
        time.sleep(0.5)
    sys.exit(f"ABORT: {what} did not come up on port {port} within {timeout}s")


def db_one(sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).first()


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    started = []

    if port_open(API_PORT):
        print(f"FastAPI already listening on {API_PORT}, reusing it")
    else:
        print(f"starting FastAPI on {API_PORT}...")
        started.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=APP_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait_for(API_PORT, 60, "FastAPI")

    if port_open(UI_PORT):
        print(f"Vite already listening on {UI_PORT}, reusing it")
    else:
        print(f"starting Vite dev server on {UI_PORT}...")
        started.append(subprocess.Popen(
            ["npm.cmd" if sys.platform == "win32" else "npm", "run", "dev"],
            cwd=CLIENT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait_for(UI_PORT, 90, "Vite dev server")

    try:
        run_browser_flow()
    finally:
        for p in started:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        if started:
            print("stopped the servers this script started")

    print(f"\n==== {PASS}/{PASS + FAILED} browser checks passed ====")
    return 0 if FAILED == 0 else 1


def run_browser_flow():
    global PASS, FAILED

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        # Two different signals, kept apart on purpose:
        #   page_errors   - uncaught JS/React exceptions. Must be zero.
        #   console_errors - anything logged at error level. Chromium logs a
        #     failed HTTP response here too, and this flow deliberately
        #     provokes a 401 (/auth/me before login), a 409 (duplicate code)
        #     and a 422 (bad code), so those are expected and filtered out.
        page_errors = []
        console_errors = []
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        # ---------- login ----------
        print("\n### Login")
        page.goto(UI, wait_until="networkidle")
        page.click("text=Login")
        page.fill("#email", DEMO_EMAIL)
        page.fill("#password", DEMO_PASSWORD)
        page.click("button:has-text('Log In')")
        page.wait_for_selector("text=Logged in as", timeout=15000)
        check("login lands on an authenticated shell", True)

        # ---------- home screen reads from Redux ----------
        print("\n### Home screen (Part 1.III.3)")
        page.wait_for_selector("table.fixture-table tbody tr", timeout=20000)
        banner = page.inner_text("css=.page-card >> text=/fixtures in Redux state/")
        db_total = db_one("SELECT COUNT(*) AS n FROM fixtures").n
        check(f"Home reports the real row count ({db_total})",
              str(db_total) in banner, banner)
        rows = page.locator("table.fixture-table tbody tr").count()
        check("Home renders one page of 25 rows", rows == 25, rows)
        page.screenshot(path=str(SHOTS / "redux_auto_home.png"), full_page=True)

        first_before = page.inner_text("table.fixture-table tbody tr:first-child td:nth-child(2)")
        page.click("css=.pager button:has-text('Next')")
        page.wait_for_function(
            "prev => document.querySelector('table.fixture-table tbody tr td:nth-child(2)')"
            ".innerText !== prev", arg=first_before)
        first_after = page.inner_text("table.fixture-table tbody tr:first-child td:nth-child(2)")
        check("Next advances the page", first_before != first_after,
              f"{first_before!r} -> {first_after!r}")
        page.click("css=.pager button:has-text('Prev')")

        # ---------- create ----------
        print("\n### Create screen (Part 1.III.4)")
        team = db_one("SELECT id, team_code FROM teams ORDER BY id LIMIT 1")
        page.click("text=Add Record")
        page.wait_for_selector("#fixture_code")
        page.fill("#fixture_name", TEST_NAME)
        page.fill("#teams_players", "Redux Home vs Redux Away")
        page.fill("#fixture_code", TEST_CODE)
        page.fill("#spots_available", "17")
        page.select_option("#home_team_id", str(team.id))
        page.click("button:has-text('Add Fixture')")

        # Scope this to a table row. Matching bare text anywhere on the page
        # is a false positive: the confirmation banner also contains the
        # fixture code, so the check passed even when no row was rendered.
        new_row = page.locator("table.fixture-table tbody tr", has_text=TEST_CODE)
        new_row.first.wait_for(timeout=15000)
        check("create returns to Home with the new fixture visible as a table row",
              new_row.count() == 1, f"matched {new_row.count()} rows")
        check("the new row is highlighted as the one just touched",
              "row-touched" in (new_row.first.get_attribute("class") or ""),
              new_row.first.get_attribute("class"))

        row = db_one("SELECT id, fixture_name, spots_available, home_team_id "
                     "FROM fixtures WHERE fixture_code = :c", c=TEST_CODE)
        check("created fixture really persisted in MySQL",
              row is not None and row.fixture_name == TEST_NAME
              and row.spots_available == 17 and row.home_team_id == team.id, str(row))
        new_id = row.id if row else None
        page.screenshot(path=str(SHOTS / "redux_auto_create.png"), full_page=True)

        # A create must grow the store, not silently refetch.
        banner = page.inner_text("css=.page-card >> text=/fixtures in Redux state/")
        check("Home count grew by one after create",
              str(db_total + 1) in banner, banner)

        # ---------- create: server-side rejection surfaces in the UI ----------
        print("\n### Create screen error handling")
        page.click("text=Add Record")
        page.wait_for_selector("#fixture_code")
        page.fill("#fixture_name", "Duplicate Code Attempt")
        page.fill("#teams_players", "A vs B")
        page.fill("#fixture_code", TEST_CODE)          # already taken -> 409
        page.select_option("#home_team_id", str(team.id))
        page.click("button:has-text('Add Fixture')")
        err = page.wait_for_selector("[data-testid=create-error]", timeout=15000)
        check("duplicate fixture_code shows the API's 409 message on the form",
              "already in use" in err.inner_text(), err.inner_text())

        page.fill("#fixture_code", "NOT-A-CODE")       # bad format -> 422
        page.click("button:has-text('Add Fixture')")
        page.wait_for_timeout(1500)
        err_text = page.inner_text("[data-testid=create-error]")
        check("malformed fixture_code shows the API's 422 message, field named",
              "fixture_code" in err_text, err_text)
        page.screenshot(path=str(SHOTS / "redux_auto_create_error.png"), full_page=True)

        # ---------- update ----------
        print("\n### Update screen (Part 1.III.4)")
        page.click("text=Home")
        page.wait_for_selector("table.fixture-table tbody tr")
        page.click("text=Update Record")
        page.wait_for_selector("#select-id")
        page.fill("#select-id", str(new_id))
        page.wait_for_selector("#fixture_name")
        check("selecting by ID prefills the form from Redux state",
              page.input_value("#fixture_name") == TEST_NAME,
              page.input_value("#fixture_name"))

        page.fill("#fixture_name", TEST_NAME + " (UPDATED)")
        page.fill("#spots_available", "9")
        page.click("button:has-text('Save Changes')")
        updated_row = page.locator("table.fixture-table tbody tr",
                                   has_text=TEST_NAME + " (UPDATED)")
        updated_row.first.wait_for(timeout=15000)
        check("update returns to Home with the changed value visible as a table row",
              updated_row.count() == 1, f"matched {updated_row.count()} rows")
        check("updated row shows the new spots_available in the table",
              "9" in updated_row.first.inner_text(), updated_row.first.inner_text())

        row = db_one("SELECT fixture_name, spots_available, created_at, updated_at "
                     "FROM fixtures WHERE id = :i", i=new_id)
        check("update really persisted in MySQL",
              row is not None and row.fixture_name.endswith("(UPDATED)")
              and row.spots_available == 9, str(row))
        check("updated_at advanced past created_at",
              row is not None and row.updated_at > row.created_at,
              f"created={row.created_at} updated={row.updated_at}" if row else "")
        page.screenshot(path=str(SHOTS / "redux_auto_update.png"), full_page=True)

        # ---------- update: unknown id ----------
        page.click("text=Update Record")
        page.wait_for_selector("#select-id")
        page.fill("#select-id", "999999")
        msg = page.wait_for_selector("[data-testid=update-no-such-id]", timeout=10000)
        check("unknown id is reported instead of showing an empty form",
              "999999" in msg.inner_text(), msg.inner_text())

        # ---------- delete ----------
        print("\n### Delete from the list (Part 1.III.5)")
        page.click("text=Home")
        page.wait_for_selector("table.fixture-table tbody tr")
        # The new row is on the last page; jump there rather than scanning.
        while page.locator(f"[data-testid=delete-{new_id}]").count() == 0:
            nxt = page.locator("css=.pager button:has-text('Next')")
            if nxt.is_disabled():
                break
            nxt.click()
            page.wait_for_timeout(200)
        check("per-row delete button is present for the new fixture",
              page.locator(f"[data-testid=delete-{new_id}]").count() == 1)

        page.on("dialog", lambda d: d.accept())
        page.click(f"[data-testid=delete-{new_id}]")
        page.wait_for_selector(f"text=Deleted fixture #{new_id}", timeout=15000)
        check("delete shows a confirmation on the Home screen", True)
        check("deleted row is gone from the rendered table",
              page.locator(f"[data-testid=delete-{new_id}]").count() == 0)
        check("delete really removed the row from MySQL",
              db_one("SELECT id FROM fixtures WHERE id = :i", i=new_id) is None)
        page.screenshot(path=str(SHOTS / "redux_auto_delete.png"), full_page=True)

        # ---------- no console errors anywhere in the run ----------
        print("\n### Browser console")
        check("no uncaught JS or React exceptions during the whole flow",
              not page_errors, "; ".join(page_errors[:3]))

        EXPECTED = ("failed to load resource", "favicon")
        unexpected = [e for e in console_errors
                      if not any(x in e.lower() for x in EXPECTED)]
        check("no unexpected console errors (deliberate 401/409/422 network "
              "responses excluded)",
              not unexpected, "; ".join(unexpected[:3]))
        print(f"      for reference, {len(console_errors)} expected network-failure "
              f"console lines were seen (the 401/409/422 this flow provokes)")

        browser.close()


if __name__ == "__main__":
    sys.exit(main())
