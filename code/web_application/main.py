"""
DATA-260 Homework 2 - Part 2: FastAPI backend
Runs on PORT_BASE (8871). Serves the home view (templates/index.html),
a small JSON API the frontend JS uses to load/search the fixture list
(driving the loading/empty/error states from Part 1), and handles
create / update-record-1 / delete-highest-id via classic HTML form
POST + redirect back to the home view.

HW4 additions: CORSMiddleware + api_v2's JSON API router (for the React
client), now backed by real MySQL tables via SQLAlchemy. On startup, the
tables are created if missing, and a demo user + starter fixtures are
seeded (only if they don't already exist).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import SessionMiddleware
import auth
import api_v2
from db import Base, engine, db_session_basede26
import models
from query_counter import register_query_counter, query_count_middleware

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Community Sports League Fixtures")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key="dev-secret-key-change-in-production",
    session_cookie="session",
    max_age=3600,
    same_site="lax",
    https_only=True,
)
app.middleware("http")(query_count_middleware)
register_query_counter(engine)

app.include_router(auth.router)
app.include_router(api_v2.router)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = db_session_basede26()
    try:
        api_v2.seed_demo_data(db)
    finally:
        db.close()


# ---------------------------------------------------------------------
# In-memory data store (HW1-3 server-rendered fixtures page - unchanged,
# still separate from the new React client's real-MySQL-backed data)
# ---------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


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


@app.get("/fixtures")
def fixtures_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/fixtures")
def list_fixtures(q: Optional[str] = None):
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
    return RedirectResponse(url="/fixtures", status_code=303)


@app.post("/fixtures/update-first")
def update_first():
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


@app.post("/fixtures/delete-highest")
def delete_highest():
    if fixtures:
        highest = max(fixtures, key=lambda f: f["id"])
        fixtures.remove(highest)
    return RedirectResponse(url="/fixtures", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8871)