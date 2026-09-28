"""
DATA-260 Homework 4 - Part 2/3: SQLAlchemy table models.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from db import Base


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_name = Column(String(255), nullable=False)
    teams_players = Column(String(255), nullable=False)

    # One-directional relationship for Part 3's N+1 demonstration.
    updates = relationship("FixtureUpdate")


class FixtureUpdate(Base):
    """Part 3 test data: a related table, 200 rows, each pointing at one
    of the 5,000 fixtures. Just test data for now - a proper related
    entity with full CRUD comes in a later homework."""
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
    password_hash = Column(String(255), nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User")