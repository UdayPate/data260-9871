"""
DATA-260 Homework 9 - Part 2: the league-database facts a question depends on, and their data-version marker.

A question that names a fixture code (FX-9871-00005) is answered from that fixture's row in s9871_rel, so the cached answer is only as
fresh as that row. lookup_facts() returns the facts, a ready-to-send facts block, and `version`: a short SHA-256 of exactly the fields
the answer can depend on. updated_at is deliberately NOT used as the marker: the column has ON UPDATE CURRENT_TIMESTAMP, so every
Part 1 view-counter sync would change it and falsely invalidate answers that did not change.

Reuses the HW4/HW5 MySQL setup (credentials/URL from web_application/db.py, tables fixtures and teams); own quiet engine as in Part 1.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web_application"))
from db import DATABASE_URL  # noqa: E402

FIXTURE_CODE = re.compile(r"\bFX-9871-\d{5}\b", re.IGNORECASE)
_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL)
    return _engine


def fixture_facts(codes: list[str]) -> dict:
    """code -> {fixture_name, teams_players, home_team, home_ground, spots_available}, or None for a code that is not in the database."""
    out = dict.fromkeys(codes)
    if not codes:
        return out
    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT f.fixture_code, f.fixture_name, f.teams_players, f.spots_available, t.team_name, t.home_ground "
            "FROM fixtures f JOIN teams t ON t.id = f.home_team_id WHERE f.fixture_code IN :codes").bindparams(
            bindparam("codes", expanding=True)), {"codes": codes}).all()
    for code, name, teams, spots, home, ground in rows:
        out[code] = {"fixture_name": name, "teams_players": teams, "home_team": home, "home_ground": ground, "spots_available": spots}
    return out


def fingerprint(facts: dict) -> str:
    """Data-version marker: SHA-256 (first 16 hex) over the facts an answer can depend on; 'static' for a question with no database facts."""
    if not facts:
        return "static"
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]


def lookup_facts(query: str) -> dict:
    codes = sorted({c.upper() for c in FIXTURE_CODE.findall(query)})
    facts = fixture_facts(codes)
    lines = []
    for code, f in facts.items():
        if f is None:
            lines.append(f"- {code}: no such fixture exists in the league database.")
        else:
            lines.append(f'- {code}: "{f["fixture_name"]}"; teams: {f["teams_players"]}; home team: {f["home_team"]} '
                         f'(home ground: {f["home_ground"]}); player spots available: {f["spots_available"]}.')
    block = ("League database facts (authoritative; use them, do not invent other values):\n" + "\n".join(lines) + "\n\n") if lines else ""
    return {"refs": codes, "facts": facts, "version": fingerprint(facts), "block": block}
