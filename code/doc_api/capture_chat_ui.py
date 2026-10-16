"""
DATA-260 Homework 6 - Part 2: drive the real mini chat page (/chat) in headless
Chromium with Playwright - real typing, real clicks - and save real screenshots
of the conversation. The server must be running on 8871.
Usage: python capture_chat_ui.py
"""

from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright
from pymongo import MongoClient

BASE = "http://127.0.0.1:8871"
USER = "uday_ui"
SHOTS = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

MESSAGES = [
    "Hi! I'm Uday and I coach the Milpitas Lions, a U12 soccer team.",
    "We play Saturday mornings at Cesar Chavez Park.",
    "My assistant coach is Priya and she can't make games in November.",
    "Our rival is the San Jose Tigers and they play on Sundays.",
    "Please remember I prefer email reminders over text messages.",
    "What do you remember about me, my team and my assistant coach?",
]

db = MongoClient("mongodb://localhost:27017", tz_aware=True)["s9871_doc"]
for coll in ("messages", "summaries", "episodes"):
    db[coll].delete_many({"user_id": USER})   # fresh conversation (UI test user only)

print("Run at", datetime.now().isoformat(timespec="seconds"))
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(f"{BASE}/chat")
    assert page.title() == "League Assistant - Memory Chat"
    for i, text in enumerate(MESSAGES, 1):
        page.fill("#msg", text)
        page.click("#send")
        # wait until the placeholder "..." is replaced and the button re-enabled
        page.wait_for_function("document.getElementById('send').disabled === false", timeout=180000)
        bots = page.locator(".msg.bot, .msg.err")
        reply = bots.nth(bots.count() - 1).inner_text()
        print(f"turn {i}: USER: {text}\n        BOT : {reply}")
        assert reply != "..." and not reply.startswith("Error"), reply
    page.screenshot(path=str(SHOTS / "part2_chat_ui.png"))

    # failure path through the real UI: an invalid user_id must show a clear error
    page.fill("#user", "bad user!")
    page.fill("#msg", "this should be rejected")
    page.click("#send")
    page.wait_for_selector(".msg.err")
    err = page.locator(".msg.err").inner_text()
    print("invalid user_id ->", err)
    assert "user_id" in err
    page.screenshot(path=str(SHOTS / "part2_chat_ui_error.png"))
    browser.close()

# persistence check, bypassing the API
n = db["messages"].count_documents({"user_id": USER})
print("Direct MongoDB: messages for", USER, "=", n)
assert n == 2 * len(MESSAGES), n
print("OK: UI conversation persisted;", len(MESSAGES), "turns")
