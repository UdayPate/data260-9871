"""
DATA-260 JSON API backend, backed by real MySQL tables via SQLAlchemy.

HW4 (Part 2/3): auth, fixture CRUD, and the N+1 measurement endpoints.
HW5 (Part 1.II): full CRUD for the new `teams` related entity (with
pagination), the extended fixture payload (unique code, spots_available,
home_team_id), the relationship query
`GET /api/teams/{team_id}/fixtures`, and explicit HTTP status codes for
resource-not-found (404), validation errors (422) and constraint
violations (409).
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession, selectinload

from db import get_db
from models import (
    Fixture,
    FixtureUpdate,
    Session as SessionModel,
    Team,
    User,
)

router = APIRouter(prefix="/api")

SESSION_COOKIE_NAME = "session_token"
SESSION_LIFETIME_HOURS = 1

DEMO_EMAIL = "league_admin@example.com"
DEMO_PASSWORD = "GoLions2026!"

# Unique-field formats, validated by Pydantic before anything reaches MySQL.
TEAM_CODE_PATTERN = r"^TM-\d{4}$"
FIXTURE_CODE_PATTERN = r"^FX-9871-\d{5}$"

DEFAULT_SPOTS_AVAILABLE = 22


def seed_demo_data(db: DBSession):
    """Runs once at startup: creates the demo admin user (with a real
    bcrypt hash) and, on a completely fresh database, two starter teams
    and two starter fixtures. Safe to call on every restart - each block
    is skipped if its rows already exist."""
    if not db.query(User).filter(User.email == DEMO_EMAIL).first():
        password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
        db.add(User(name="League Admin", email=DEMO_EMAIL, password_hash=password_hash))
        db.commit()

    # A fixture now requires a home team, so teams have to exist first.
    if db.query(Team).count() == 0:
        db.add_all([
            Team(team_name="Milpitas Lions", home_ground="Milpitas Sports Complex, Field 1",
                 team_code="TM-0001"),
            Team(team_name="San Jose Tigers", home_ground="Watson Park, San Jose",
                 team_code="TM-0002"),
        ])
        db.commit()

    if db.query(Fixture).count() == 0:
        lions = db.query(Team).filter(Team.team_code == "TM-0001").first()
        tigers = db.query(Team).filter(Team.team_code == "TM-0002").first()
        db.add_all([
            Fixture(fixture_name="Lions vs Tigers",
                    teams_players="Milpitas Lions vs San Jose Tigers",
                    fixture_code="FX-9871-00001", spots_available=22,
                    home_team_id=lions.id),
            Fixture(fixture_name="Warriors vs Strikers",
                    teams_players="Milpitas Warriors vs San Jose Strikers",
                    fixture_code="FX-9871-00002", spots_available=22,
                    home_team_id=tigers.id),
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
# HW5 Part 1.II - Pydantic request/response schemas
# ---------------------------------------------------------------------

class TeamCreate(BaseModel):
    team_name: str = Field(min_length=2, max_length=255)
    home_ground: str = Field(min_length=2, max_length=255)
    team_code: str = Field(pattern=TEAM_CODE_PATTERN, max_length=20)


class TeamUpdateRequest(BaseModel):
    team_name: str = Field(min_length=2, max_length=255)
    home_ground: str = Field(min_length=2, max_length=255)
    team_code: str = Field(pattern=TEAM_CODE_PATTERN, max_length=20)


class FixtureCreate(BaseModel):
    fixture_name: str = Field(min_length=2, max_length=255)
    teams_players: str = Field(min_length=2, max_length=255)
    fixture_code: str = Field(pattern=FIXTURE_CODE_PATTERN, max_length=24)
    spots_available: int = Field(default=DEFAULT_SPOTS_AVAILABLE, ge=0, le=999)
    home_team_id: int = Field(ge=1)


class FixtureUpdateRequest(BaseModel):
    """Named ...Request so it cannot shadow models.FixtureUpdate, which is
    the SQLAlchemy table used by the HW4 N+1 endpoints below."""
    fixture_name: str = Field(min_length=2, max_length=255)
    teams_players: str = Field(min_length=2, max_length=255)
    fixture_code: str = Field(pattern=FIXTURE_CODE_PATTERN, max_length=24)
    spots_available: int = Field(default=DEFAULT_SPOTS_AVAILABLE, ge=0, le=999)
    home_team_id: int = Field(ge=1)


def team_to_dict(t: Team):
    return {
        "id": t.id,
        "team_name": t.team_name,
        "home_ground": t.home_ground,
        "team_code": t.team_code,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def fixture_to_dict(f: Fixture):
    return {
        "id": f.id,
        "fixture_name": f.fixture_name,
        "teams_players": f.teams_players,
        "fixture_code": f.fixture_code,
        "spots_available": f.spots_available,
        "home_team_id": f.home_team_id,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


# ---------------------------------------------------------------------
# HW5 Part 1.II - Teams CRUD (the related entity)
# ---------------------------------------------------------------------

@router.post("/teams", status_code=201)
def create_team(
    payload: TeamCreate,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    if db.query(Team).filter(Team.team_code == payload.team_code).first():
        raise HTTPException(
            status_code=409,
            detail=f"team_code '{payload.team_code}' is already in use",
        )
    team = Team(
        team_name=payload.team_name,
        home_ground=payload.home_ground,
        team_code=payload.team_code,
    )
    db.add(team)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race against a concurrent insert of the same code.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"team_code '{payload.team_code}' is already in use",
        )
    db.refresh(team)
    return team_to_dict(team)


@router.get("/teams")
def list_teams(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Paginated list of teams. Returns an envelope rather than a bare
    array so the client can tell how many pages there are."""
    total = db.query(Team).count()
    rows = (
        db.query(Team)
        .order_by(Team.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "items": [team_to_dict(t) for t in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@router.get("/teams/{team_id}")
def get_team(
    team_id: int,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    return team_to_dict(team)


@router.put("/teams/{team_id}")
def update_team(
    team_id: int,
    payload: TeamUpdateRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    clash = (
        db.query(Team)
        .filter(Team.team_code == payload.team_code, Team.id != team_id)
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"team_code '{payload.team_code}' is already in use by team {clash.id}",
        )

    team.team_name = payload.team_name
    team.home_ground = payload.home_ground
    team.team_code = payload.team_code
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"team_code '{payload.team_code}' is already in use",
        )
    db.refresh(team)
    return team_to_dict(team)


@router.delete("/teams/{team_id}")
def delete_team(
    team_id: int,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """A team that is still the home team of at least one fixture cannot
    be deleted - this is checked here (409) and independently enforced by
    the ON DELETE RESTRICT foreign key in MySQL, so the rule holds even
    for a DELETE issued straight against the database."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    dependents = db.query(Fixture).filter(Fixture.home_team_id == team_id).count()
    if dependents:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Team {team_id} still has {dependents} associated fixture(s) "
                "and cannot be deleted"
            ),
        )

    db.delete(team)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Team {team_id} is still referenced by fixtures and cannot be deleted",
        )
    return {"success": True, "deleted_id": team_id}


@router.get("/teams/{team_id}/fixtures")
def list_fixtures_for_team(
    team_id: int,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """HW5 Part 1.II relationship query: every fixture whose home team is
    this team."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    rows = (
        db.query(Fixture)
        .filter(Fixture.home_team_id == team_id)
        .order_by(Fixture.id)
        .all()
    )
    return {
        "team": team_to_dict(team),
        "fixture_count": len(rows),
        "fixtures": [fixture_to_dict(f) for f in rows],
    }


# ---------------------------------------------------------------------
# Fixtures CRUD (the primary domain entity - all routes require a session)
# ---------------------------------------------------------------------

def require_team(db: DBSession, team_id: int) -> Team:
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(
            status_code=404, detail=f"home_team_id {team_id} does not refer to an existing team"
        )
    return team


@router.get("/fixtures")
def list_fixtures(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixtures = db.query(Fixture).order_by(Fixture.id).all()
    return [fixture_to_dict(f) for f in fixtures]


@router.get("/fixtures/{fixture_id}")
def get_fixture(fixture_id: int, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")
    return fixture_to_dict(fixture)


@router.post("/fixtures", status_code=201)
def create_fixture(payload: FixtureCreate, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    require_team(db, payload.home_team_id)

    if db.query(Fixture).filter(Fixture.fixture_code == payload.fixture_code).first():
        raise HTTPException(
            status_code=409,
            detail=f"fixture_code '{payload.fixture_code}' is already in use",
        )

    fixture = Fixture(
        fixture_name=payload.fixture_name,
        teams_players=payload.teams_players,
        fixture_code=payload.fixture_code,
        spots_available=payload.spots_available,
        home_team_id=payload.home_team_id,
    )
    db.add(fixture)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"fixture_code '{payload.fixture_code}' is already in use",
        )
    db.refresh(fixture)
    return fixture_to_dict(fixture)


@router.put("/fixtures/{fixture_id}")
def update_fixture(fixture_id: int, payload: FixtureUpdateRequest, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")

    require_team(db, payload.home_team_id)

    clash = (
        db.query(Fixture)
        .filter(Fixture.fixture_code == payload.fixture_code, Fixture.id != fixture_id)
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"fixture_code '{payload.fixture_code}' is already in use by fixture {clash.id}",
        )

    fixture.fixture_name = payload.fixture_name
    fixture.teams_players = payload.teams_players
    fixture.fixture_code = payload.fixture_code
    fixture.spots_available = payload.spots_available
    fixture.home_team_id = payload.home_team_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"fixture_code '{payload.fixture_code}' is already in use",
        )
    db.refresh(fixture)
    return fixture_to_dict(fixture)


@router.delete("/fixtures/{fixture_id}")
def delete_fixture(fixture_id: int, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")
    db.delete(fixture)
    db.commit()
    return {"success": True, "deleted_id": fixture_id}


# ---------------------------------------------------------------------
# HW4 Part 3: N+1 measurement endpoints (unchanged)
# ---------------------------------------------------------------------

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
