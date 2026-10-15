"""
DATA-260 Homework 6 - Part 1.III: Pydantic data models / validation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(str, Enum):
    soccer = "Soccer"
    basketball = "Basketball"
    volleyball = "Volleyball"
    cricket = "Cricket"


class Status(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class FixtureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    status: Status = Status.scheduled
    category: Category
    match_date: datetime

    @field_validator("fixture_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("fixture_name must not be blank")
        return v


class FixtureUpdate(FixtureCreate):
    """PUT is a full replacement, so it has the same rules as create."""


class FixtureOut(BaseModel):
    id: str
    fixture_name: str
    description: Optional[str] = None
    status: Status
    category: Category
    match_date: datetime
    created_at: datetime
    updated_at: datetime
