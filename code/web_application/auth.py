"""
DATA-260 Homework 3 - Part 1: Authentication router
Implements Home, Login, Dashboard, and Logout routes for the Community
Sports League Fixtures domain, using Starlette's SessionMiddleware for
session cookies plus a small server-side session store so that logout
and idle timeout can be genuinely enforced (not just clearing the
client-side cookie, which alone cannot prevent replay of an
already-issued cookie).
"""

import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

IDLE_TIMEOUT_SECONDS = 30

# Single hardcoded demo account
VALID_USERNAME = "league_admin"
VALID_PASSWORD = "GoLions2026!"

# Server-side session store: session_id -> {"username": ..., "last_activity": float}
# This is what makes logout and idle-timeout ACTUALLY enforceable - a signed
# session cookie alone can still be replayed after "logout" unless the server
# independently tracks which session ids are currently valid.
ACTIVE_SESSIONS = {}


def get_current_user(request: Request):
    """Returns the logged-in username if the session is valid and has not
    idle-timed-out. Otherwise revokes/clears the session and returns None."""
    sid = request.session.get("sid")
    if not sid or sid not in ACTIVE_SESSIONS:
        request.session.clear()
        return None

    session_data = ACTIVE_SESSIONS[sid]
    if time.time() - session_data["last_activity"] > IDLE_TIMEOUT_SECONDS:
        del ACTIVE_SESSIONS[sid]
        request.session.clear()
        return None

    # Still valid - sliding idle timeout: refresh on activity
    session_data["last_activity"] = time.time()
    return session_data["username"]


@router.get("/")
def home(request: Request):
    username = get_current_user(request)
    return templates.TemplateResponse(request, "home.html", {"username": username})


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "username": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == VALID_USERNAME and password == VALID_PASSWORD:
        sid = secrets.token_hex(16)
        ACTIVE_SESSIONS[sid] = {"username": username, "last_activity": time.time()}
        request.session["sid"] = sid
        return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid username or password.", "username": None},
        status_code=401,
    )


@router.get("/dashboard")
def dashboard(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"username": username})


@router.get("/logout")
def logout(request: Request):
    sid = request.session.get("sid")
    if sid and sid in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[sid]
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)