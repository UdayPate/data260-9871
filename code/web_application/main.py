"""
DATA-260 Homework 2 - Part 2: FastAPI backend
Runs on PORT_BASE (8871). Serves the home view (templates/index.html),
a small JSON API the frontend JS uses to load/search the fixture list
(driving the loading/empty/error states from Part 1), and handles
create / update-record-1 / delete-highest-id via classic HTML form
POST + redirect back to the home view.

Data is stored in-memory (a plain Python list) - it resets whenever
the server restarts. That's an intentional, documented simplification;
the assignment doesn't require persistence.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware
import auth

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Community Sports League Fixtures")

app.add_middleware(
    SessionMiddleware,
    secret_key="dev-secret-key-change-in-production",
    session_cookie="session",
    max_age=3600,
    same_site="lax",
    https_only=True,
)
app.include_router(auth.router)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------------------------------------------------------------------
# In-memory data store
# ---------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# Seeded with two records so "update record ID 1" and "delete the
# highest-ID record" both have something real to act on immediately.
fixtures = [
    {
        "id": 1,
        "fixture_name": "Lions vs Tigers",
        "teams_players": "Milpitas Lions vs San Jose Tigers",
        "submitter_email": "captain@leaguemail.com",
        "description": "Season opener. Bring your own water bottles.",
        "category": "soccer",
        "agree_terms": True,
        "submitted": now_iso(),
    },
    {
        "id": 2,
        "fixture_name": "Warriors vs Strikers",
        "teams_players": "Milpitas Warriors vs San Jose Strikers",
        "submitter_email": "admin@leaguemail.com",
        "description": "Rivalry match, gates open 9am, toss at 9:30am.",
        "category": "cricket",
        "agree_terms": True,
        "submitted": now_iso(),
    },
]
next_id = 3


# ---------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------

@app.get("/fixtures")
def fixtures_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


# ---------------------------------------------------------------------
# JSON API - used by the frontend JS for loading the list and search
# ---------------------------------------------------------------------

@app.get("/api/fixtures")
def list_fixtures(q: Optional[str] = None):
    """Returns the fixture list as JSON, optionally filtered by a
    case-insensitive match against fixture_name or teams_players."""
    if q:
        q_lower = q.lower()
        results = [
            f for f in fixtures
            if q_lower in f["fixture_name"].lower()
            or q_lower in f["teams_players"].lower()
        ]
    else:
        results = fixtures
    return JSONResponse(content=results)


# ---------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------

@app.post("/fixtures/create")
def create_fixture(
    fixture_name: str = Form(...),
    teams_players: str = Form(...),
    submitter_email: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    agree_terms: Optional[str] = Form(None),
):
    global next_id
    fixtures.append({
        "id": next_id,
        "fixture_name": fixture_name,
        "teams_players": teams_players,
        "submitter_email": submitter_email,
        "description": description,
        "category": category,
        "agree_terms": agree_terms == "on",
        "submitted": now_iso(),
    })
    next_id += 1
    # 303 See Other is the correct redirect status after a POST,
    # so the browser follows up with a GET rather than re-POSTing.
    return RedirectResponse(url="/fixtures", status_code=303)


# ---------------------------------------------------------------------
# Update record with ID 1
# ---------------------------------------------------------------------

@app.post("/fixtures/update-first")
def update_first():
    """Updates the record with ID 1 to new domain-appropriate values.
    This is a fixed, one-click action per the assignment's wording,
    not a general "edit any record" form."""
    for f in fixtures:
        if f["id"] == 1:
            f["fixture_name"] = "Lions vs Tigers - RESCHEDULED"
            f["teams_players"] = "Milpitas Lions vs San Jose Tigers (new roster)"
            f["submitter_email"] = "league-office@leaguemail.com"
            f["description"] = "Match moved to Sunday due to field maintenance."
            f["category"] = "soccer"
            f["agree_terms"] = True
            f["submitted"] = now_iso()
            break
    return RedirectResponse(url="/fixtures", status_code=303)


# ---------------------------------------------------------------------
# Delete the highest-ID record
# ---------------------------------------------------------------------

@app.post("/fixtures/delete-highest")
def delete_highest():
    if fixtures:
        highest = max(fixtures, key=lambda f: f["id"])
        fixtures.remove(highest)
    return RedirectResponse(url="/fixtures", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8871)