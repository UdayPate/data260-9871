"""
DATA-260 Homework 6 - Part 1.II: CRUD route handlers for /api/fixtures.
"""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Response
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError, WriteError

import db
from schemas import FixtureCreate, FixtureOut, FixtureUpdate

router = APIRouter(prefix="/api/fixtures", tags=["fixtures"])


def _oid(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"'{raw}' is not a valid fixture id")


def _out(doc: dict) -> FixtureOut:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return FixtureOut(**doc)


def _payload(model) -> dict:
    data = model.model_dump(mode="python")
    data["status"] = model.status.value
    data["category"] = model.category.value
    if data.get("description") is None:
        data.pop("description", None)
    return data


@router.post("", response_model=FixtureOut, status_code=201)
def create_fixture(body: FixtureCreate):
    now = datetime.now(timezone.utc)
    doc = {**_payload(body), "created_at": now, "updated_at": now}
    try:
        res = db.fixtures().insert_one(doc)
    except WriteError as exc:
        raise HTTPException(status_code=422, detail=f"database validation failed: {exc}")
    doc["_id"] = res.inserted_id
    return _out(doc)


@router.get("", response_model=list[FixtureOut])
def list_fixtures():
    return [_out(d) for d in db.fixtures().find().sort("match_date", 1)]


@router.get("/{fixture_id}", response_model=FixtureOut)
def get_fixture(fixture_id: str):
    doc = db.fixtures().find_one({"_id": _oid(fixture_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return _out(doc)


@router.put("/{fixture_id}", response_model=FixtureOut)
def update_fixture(fixture_id: str, body: FixtureUpdate):
    data = _payload(body)
    update = {"$set": {**data, "updated_at": datetime.now(timezone.utc)}}
    if "description" not in data:
        update["$unset"] = {"description": ""}
    try:
        doc = db.fixtures().find_one_and_update(
            {"_id": _oid(fixture_id)}, update, return_document=ReturnDocument.AFTER)
    except WriteError as exc:
        raise HTTPException(status_code=422, detail=f"database validation failed: {exc}")
    if doc is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return _out(doc)


@router.delete("/{fixture_id}", status_code=204)
def delete_fixture(fixture_id: str):
    res = db.fixtures().delete_one({"_id": _oid(fixture_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="fixture not found")
    return Response(status_code=204)
