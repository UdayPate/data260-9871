"""
DATA-260 SQLAlchemy table models.

HW4 (Part 2/3): fixtures, fixture_updates, users, sessions.
HW5 (Part 1.I): adds the `teams` related-entity table and extends
`fixtures` with a unique code, a defaulted numeric field, a foreign key
to teams, and timestamps.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from db import Base


class Team(Base):
    """HW5 Part 1.I related entity - the "author"-role table.

    One team is the *home* team for many fixtures. A fixture in this
    domain involves two sides, but the assignment asks for a single
    foreign key, so `fixtures.home_team_id` deliberately models only the
    home side; the away side stays in the free-text `teams_players`
    field. That limitation is documented rather than hidden.

    Deleting a team that still has fixtures is refused - the foreign key
    is ON DELETE RESTRICT at the database level and the API also returns
    409 before it ever reaches MySQL (see api_v2.delete_team).
    """

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_name = Column(String(255), nullable=False)                 # primary text field
    home_ground = Column(String(255), nullable=False)               # secondary text field
    team_code = Column(String(20), nullable=False, unique=True)     # unique field, format TM-XXXX
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    fixtures = relationship("Fixture", back_populates="home_team")


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_name = Column(String(255), nullable=False)              # primary field
    teams_players = Column(String(255), nullable=False)

    # --- HW5 Part 1.I additions ---
    fixture_code = Column(String(24), nullable=False, unique=True)  # unique field, FX-9871-#####
    # "available count" style numeric field: remaining player sign-up
    # spots. 22 = a full two-side roster, the sensible default here.
    spots_available = Column(
        Integer, nullable=False, server_default="22", default=22
    )
    home_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    home_team = relationship("Team", back_populates="fixtures")

    # One-directional relationship kept from HW4's N+1 demonstration.
    updates = relationship("FixtureUpdate")


class FixtureUpdate(Base):
    """HW4 Part 3 test data: 200 rows, each pointing at one of the
    5,000 seeded fixtures. Used only by the N+1 measurement endpoints."""

    __tablename__ = "fixture_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    note = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    # bcrypt hash only - no plain-text password is ever stored.
    password_hash = Column(String(255), nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User")
