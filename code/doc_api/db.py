"""
DATA-260 Homework 6 - Part 1: PyMongo connection + collection validator.
The Pydantic schema is the first line of defence; the $jsonSchema validator
installed here is the database-level backstop (it rejects bad writes even
if something bypasses the API).
"""

from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

import config

CATEGORIES = ["Soccer", "Basketball", "Volleyball", "Cricket"]
STATUSES = ["scheduled", "in_progress", "completed", "cancelled"]

_client = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=3000, tz_aware=True)
    return _client


def get_db():
    return get_client()[config.MONGO_DB]


def fixtures():
    return get_db()[config.FIXTURES_COLLECTION]


FIXTURE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["fixture_name", "status", "category", "match_date",
                     "created_at", "updated_at"],
        "properties": {
            "fixture_name": {"bsonType": "string", "minLength": 1, "maxLength": 100},
            "description": {"bsonType": "string", "maxLength": 2000},
            "status": {"enum": STATUSES},
            "category": {"enum": CATEGORIES},
            "match_date": {"bsonType": "date"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}


def init_db() -> None:
    """Create the fixtures collection with its validator (idempotent)."""
    db = get_db()
    name = config.FIXTURES_COLLECTION
    if name not in db.list_collection_names():
        db.create_collection(name, validator=FIXTURE_VALIDATOR,
                             validationLevel="strict", validationAction="error")
    else:
        db.command("collMod", name, validator=FIXTURE_VALIDATOR,
                   validationLevel="strict", validationAction="error")
    db[name].create_index([("match_date", ASCENDING)])
    db[name].create_index([("category", ASCENDING), ("status", ASCENDING)])
