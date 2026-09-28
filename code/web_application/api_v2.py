"""
DATA-260 Homework 4 - Part 2: JSON API backend, now backed by real MySQL
tables via SQLAlchemy instead of in-memory dicts. Same API shape as the
earlier in-memory version - no changes needed on the React side.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from db import get_db
from models import Fixture, User, Session as SessionModel

router = APIRouter(prefix="/api")

SESSION_COOKIE_NAME = "session_token"
SESSION_LIFETIME_HOURS = 1

DEMO_EMAIL = "league_admin@example.com"
DEMO_PASSWORD = "GoLions2026!"


def seed_demo_data(db: DBSession):
    """Runs once at startup: creates the demo admin user (with a real
    bcrypt hash) and two starter fixtures, but ONLY if they don't
    already exist - safe to call on every restart."""
    if not db.query(User).filter(User.email == DEMO_EMAIL).first():
        password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
        db.add(User(name="League Admin", email=DEMO_EMAIL, password_hash=password_hash))
        db.commit()

    if db.query(Fixture).count() == 0:
        db.add_all([
            Fixture(fixture_name="Lions vs Tigers", teams_players="Milpitas Lions vs San Jose Tigers"),
            Fixture(fixture_name="Warriors vs Strikers", teams_players="Milpitas Warriors vs San Jose Strikers"),
        ])
        db.commit()


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


def get_current_user(
    session_token: Optional[str] = Cookie(default=None),
    db: DBSession = Depends(get_db),
):
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.query(SessionModel).filter(SessionModel.id == session_token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not bcrypt.checkpw(payload.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_hex(16)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=SESSION_LIFETIME_HOURS)
    db.add(SessionModel(id=token, user_id=user.id, expires_at=expires_at))
    db.commit()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=3600,
        path="/",
    )
    return {"id": user.id, "name": user.name, "email": user.email}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email}


@router.post("/auth/logout")
def logout(
    response: Response,
    session_token: Optional[str] = Cookie(default=None),
    db: DBSession = Depends(get_db),
):
    if session_token:
        session = db.query(SessionModel).filter(SessionModel.id == session_token).first()
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"success": True}


# ---------------------------------------------------------------------
# Fixtures CRUD (all protected - require a valid session)
# ---------------------------------------------------------------------

class FixtureCreate(BaseModel):
    fixture_name: str
    teams_players: str


class FixtureUpdate(BaseModel):
    fixture_name: str
    teams_players: str


def fixture_to_dict(f: Fixture):
    return {"id": f.id, "fixture_name": f.fixture_name, "teams_players": f.teams_players}


@router.get("/fixtures")
def list_fixtures(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixtures = db.query(Fixture).all()
    return [fixture_to_dict(f) for f in fixtures]


@router.get("/fixtures/{fixture_id}")
def get_fixture(fixture_id: int, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture_to_dict(fixture)


@router.post("/fixtures")
def create_fixture(payload: FixtureCreate, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = Fixture(fixture_name=payload.fixture_name, teams_players=payload.teams_players)
    db.add(fixture)
    db.commit()
    db.refresh(fixture)
    return fixture_to_dict(fixture)


@router.put("/fixtures/{fixture_id}")
def update_fixture(fixture_id: int, payload: FixtureUpdate, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    fixture.fixture_name = payload.fixture_name
    fixture.teams_players = payload.teams_players
    db.commit()
    db.refresh(fixture)
    return fixture_to_dict(fixture)


@router.delete("/fixtures/{fixture_id}")
def delete_fixture(fixture_id: int, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    db.delete(fixture)
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------------
# Part 3: N+1 measurement endpoints
# ---------------------------------------------------------------------

from sqlalchemy.orm import selectinload
from models import FixtureUpdate


def fixture_with_updates_to_dict(f: Fixture):
    return {
        "id": f.id,
        "fixture_name": f.fixture_name,
        "teams_players": f.teams_players,
        "updates": [u.note for u in f.updates],
    }


@router.get("/fixtures-naive")
def list_fixtures_naive(
    request: Request,
    page_size: int = 10,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Intentionally naive: fetches the page of fixtures with ONE query,
    then fires ONE ADDITIONAL query per fixture to fetch its related
    updates - the classic N+1 problem. Total queries = 1 + page_size."""
    # Reset the counter explicitly - Connection.info persists at the
    # pooled-connection level across checkouts, so it must be zeroed
    # here rather than assumed to start fresh each request.
    db.connection().info["query_count"] = 0
    fixtures = db.query(Fixture).limit(page_size).all()
    results = []
    for f in fixtures:
        updates = db.query(FixtureUpdate).filter(FixtureUpdate.fixture_id == f.id).all()
        results.append({
            "id": f.id,
            "fixture_name": f.fixture_name,
            "teams_players": f.teams_players,
            "updates": [u.note for u in updates],
        })
    request.state.sql_query_count = db.connection().info.get("query_count", 0)
    return results


@router.get("/fixtures-fixed")
def list_fixtures_fixed(
    request: Request,
    page_size: int = 10,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Fixed: uses selectinload to eager-load each fixture's related
    updates in a SECOND single query (using WHERE fixture_id IN (...)),
    instead of one query per fixture. Total queries = 2, regardless of
    page_size."""
    db.connection().info["query_count"] = 0
    fixtures = db.query(Fixture).options(selectinload(Fixture.updates)).limit(page_size).all()
    results = [fixture_with_updates_to_dict(f) for f in fixtures]
    request.state.sql_query_count = db.connection().info.get("query_count", 0)
    return results