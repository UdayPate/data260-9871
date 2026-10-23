"""
DATA-260 Homework 7 - Part 1: real-browser test of the JWT-aware React client (Playwright).

Complements test_redux_ui.py (which exercises the moderator's full create/update/delete flow). This one
checks what the move from session cookies to bearer tokens changed in the UI: who sees which controls, what
a wrong password shows, that the token is kept in sessionStorage, and that a bad/expired token sends the
user back to the login screen. It starts the API and Vite if they are not already running.

Run from code/web_application, inside the venv:   python test_jwt_ui.py
"""

import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from playwright.sync_api import sync_playwright

import db  # noqa: F401  (loads .env so JWT_SECRET is available for building an expired token)
import os

APP_DIR = Path(__file__).resolve().parent
UI = "http://localhost:5173"
USERS = {"reader": ("reader_user", "Reader2026!"), "writer": ("writer_user", "Writer2026!"),
         "moderator": ("moderator_user", "Moderator2026!")}
PASS = FAILED = 0


def check(label, cond, extra=""):
    global PASS, FAILED
    PASS += bool(cond)
    FAILED += not cond
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"   ({extra})" if extra and not cond else ""), flush=True)


def port_open(port):
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for(port, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if port_open(port):
            return
        time.sleep(0.5)
    sys.exit(f"ABORT: nothing listening on {port}")


def login(page, username, password):
    page.goto(UI, wait_until="networkidle")
    page.evaluate("sessionStorage.clear()")
    page.goto(UI, wait_until="networkidle")
    page.click("text=Login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button:has-text('Log In')")


def main():
    started = []
    if not port_open(8871):
        started.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8871"],
                                        cwd=APP_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait_for(8871, 60)
    if not port_open(5173):
        started.append(subprocess.Popen(["npm.cmd" if sys.platform == "win32" else "npm", "run", "dev"],
                                        cwd=APP_DIR / "client", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait_for(5173, 90)
    print("Run at", datetime.now().isoformat(timespec="seconds"))
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 900})
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            print("\n### wrong password / unknown user")
            login(page, "writer_user", "wrong-password")
            page.wait_for_selector("[data-testid=login-error]", timeout=10000)
            check("wrong password shows the API's 401 message on the form", "Invalid username or password" in page.inner_text("[data-testid=login-error]"))
            check("no token was stored after a failed login", page.evaluate("sessionStorage.getItem('hw7_access_token')") is None)

            for role, (u, p) in USERS.items():
                print(f"\n### logged in as {role}")
                login(page, u, p)
                page.wait_for_selector("text=Logged in as", timeout=15000)
                page.wait_for_selector("table.fixture-table tbody tr", timeout=20000)
                tag = page.inner_text(".user-tag")
                check(f"{role}: nav shows username and role", u in tag and f"({role})" in tag, tag)
                check(f"{role}: JWT is kept in sessionStorage (3 dot-separated parts)",
                      (page.evaluate("sessionStorage.getItem('hw7_access_token')") or "").count(".") == 2)
                check(f"{role}: no cookie is used for auth", not any(c["name"] == "session_token" for c in page.context.cookies()))
                add = page.locator("nav >> text=Add Record").count()
                dele = page.locator("[data-testid^=delete-]").count()
                edit = page.locator("table.fixture-table >> text=Edit").count()
                check(f"{role}: 'Add Record' link {'hidden' if role == 'reader' else 'visible'}", (add == 0) == (role == "reader"))
                check(f"{role}: row 'Edit' links {'hidden' if role == 'reader' else 'visible'}", (edit == 0) == (role == "reader"))
                check(f"{role}: Delete buttons {'visible' if role == 'moderator' else 'hidden'}", (dele > 0) == (role == "moderator"))
                if role == "reader":
                    page.goto(UI + "/create", wait_until="networkidle")
                    check("reader typing /create in the URL is redirected away", "/create" not in page.url)
                page.click("button:has-text('Log out')")
                page.wait_for_selector("text=Login", timeout=10000)
                check(f"{role}: logout forgets the token", page.evaluate("sessionStorage.getItem('hw7_access_token')") is None)

            print("\n### invalid and expired tokens")
            login(page, *USERS["writer"])
            page.wait_for_selector("text=Logged in as", timeout=15000)
            uid = jwt.decode(page.evaluate("sessionStorage.getItem('hw7_access_token')"), options={"verify_signature": False})["sub"]
            now = datetime.now(timezone.utc)
            expired = jwt.encode({"sub": uid, "iat": now - timedelta(minutes=40), "exp": now - timedelta(minutes=10)},
                                 os.environ["JWT_SECRET"], algorithm="HS256")
            for label, token in (("an EXPIRED token", expired), ("a garbage token", "not.a.jwt")):
                page.evaluate("t => sessionStorage.setItem('hw7_access_token', t)", token)
                page.reload(wait_until="networkidle")
                check(f"{label} in storage: page falls back to the logged-out shell (Login link shown)",
                      page.locator("nav >> text=Login").count() == 1 and page.locator(".user-tag").count() == 0)
                check(f"{label}: the bad token was discarded", page.evaluate("sessionStorage.getItem('hw7_access_token')") is None)
            check("no uncaught JS/React exceptions during the whole flow", not page_errors, "; ".join(page_errors[:2]))
            browser.close()
    finally:
        for proc in started:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    print(f"\n==== {PASS}/{PASS + FAILED} browser checks passed ====")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
