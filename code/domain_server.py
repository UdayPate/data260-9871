"""
DATA-260 Homework 5 - Part 2B: domain MCP server over s9871_rel.

A local MCP server named "domain" exposing exactly three tools over STDIO,
each returning the {ok, data, error} envelope this homework reuses in
Part 4's execute_tool:

    search_fixtures(query, limit=10)   - search
    fixture_details(id)                - detail lookup
    team_fixture_counts(min_fixtures=0) - aggregate (fixtures per team)

Run it with the MCP Inspector from the repo root (forward slashes - see
the CLAUDE.md gotcha about mcp dev mangling backslash paths):
    mcp dev code/domain_server.py --with typer

LOGGING RULE: STDIO server, so stdout is the JSON-RPC channel. All
diagnostics go to stderr via the logger below.

ERROR RULE: invalid input does NOT raise - it returns
{"ok": false, "data": null, "error": "..."} like a normal result. That is
what makes the envelope meaningful for Part 3 (documenting rejected calls)
and Part 4 (execute_tool wraps these same three tools). A result() helper
builds every response so the shape can't drift between tools.
"""

import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import func

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s [domain] %(message)s",
)
log = logging.getLogger("domain")

# Reuse the existing SQLAlchemy models/session instead of a second DB layer.
sys.path.insert(0, str(Path(__file__).resolve().parent / "web_application"))
from db import db_session_basede26  # noqa: E402
from models import Fixture, Team  # noqa: E402

mcp = MCPServer("domain", dependencies=["sqlalchemy", "pymysql"])


def result(data: Any = None, error: str | None = None) -> dict:
    """The one envelope shape every domain tool returns."""
    return {"ok": error is None, "data": data, "error": error}


def fixture_card(f: Fixture) -> dict:
    return {
        "id": f.id,
        "fixture_name": f.fixture_name,
        "teams_players": f.teams_players,
        "fixture_code": f.fixture_code,
        "spots_available": f.spots_available,
        "home_team_id": f.home_team_id,
    }


@mcp.tool()
def search_fixtures(query: str, limit: int = 10) -> dict:
    """Search fixtures by name or teams_players (case-insensitive substring).
    Returns the {ok, data, error} envelope; data is a list of fixture cards.
    """
    if not query or not query.strip():
        return result(error="query must not be empty")
    if not 1 <= limit <= 100:
        return result(error=f"limit must be between 1 and 100, got {limit}")

    db = db_session_basede26()
    try:
        like = f"%{query.strip()}%"
        rows = (
            db.query(Fixture)
            .filter(
                (Fixture.fixture_name.ilike(like)) | (Fixture.teams_players.ilike(like))
            )
            .order_by(Fixture.id)
            .limit(limit)
            .all()
        )
        log.info("search_fixtures query=%r limit=%d -> %d rows", query, limit, len(rows))
        return result(data=[fixture_card(f) for f in rows])
    finally:
        db.close()


@mcp.tool()
def fixture_details(id: int) -> dict:
    """Look up one fixture by id, including its home team. Returns the
    {ok, data, error} envelope; data is a single object."""
    if id is None or id < 1:
        return result(error=f"id must be a positive integer, got {id!r}")

    db = db_session_basede26()
    try:
        f = db.query(Fixture).filter(Fixture.id == id).first()
        if not f:
            log.info("fixture_details id=%s -> not found", id)
            return result(error=f"fixture {id} not found")
        team = db.query(Team).filter(Team.id == f.home_team_id).first()
        data = fixture_card(f)
        data["home_team"] = (
            {"id": team.id, "team_code": team.team_code, "team_name": team.team_name}
            if team
            else None
        )
        log.info("fixture_details id=%s -> found", id)
        return result(data=data)
    finally:
        db.close()


@mcp.tool()
def team_fixture_counts(min_fixtures: int = 0) -> dict:
    """Aggregate: number of fixtures hosted by each team, optionally
    filtered to teams with at least min_fixtures. Returns the
    {ok, data, error} envelope; data is a list of {team, fixture_count}."""
    if min_fixtures < 0:
        return result(error=f"min_fixtures must be >= 0, got {min_fixtures}")

    db = db_session_basede26()
    try:
        teams = db.query(Team).order_by(Team.id).all()
        rows = (
            db.query(Fixture.home_team_id, func.count(Fixture.id))
            .group_by(Fixture.home_team_id)
            .all()
        )
        counts = dict(rows)

        data = [
            {
                "team_id": t.id,
                "team_code": t.team_code,
                "team_name": t.team_name,
                "fixture_count": counts.get(t.id, 0),
            }
            for t in teams
            if counts.get(t.id, 0) >= min_fixtures
        ]
        log.info("team_fixture_counts min_fixtures=%d -> %d teams", min_fixtures, len(data))
        return result(data=data)
    finally:
        db.close()


if __name__ == "__main__":
    log.info("starting domain MCP server on stdio")
    mcp.run(transport="stdio")
