"""
DATA-260 Homework 6 - Part 1 live test: hits the running API with real HTTP
(including failure paths), then checks MongoDB directly, bypassing the API.
Usage: python test_part1.py   (server must be running on 8871)
"""

import json
import sys
from datetime import datetime

import requests
from pymongo import MongoClient

BASE = "http://127.0.0.1:8871/api/fixtures"
results = []


def show(label, r):
    body = r.text if r.text else "<empty body>"
    print(f"\n### {label}\n-> HTTP {r.status_code}\n{body[:700]}")
    return r


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


good = {"fixture_name": "Milpitas Lions vs San Jose Tigers",
        "description": "Season opener, 7 a side", "category": "Soccer",
        "match_date": "2026-11-01T18:00:00Z"}

print("Run at", datetime.now().isoformat(timespec="seconds"))
r = show("POST valid fixture", requests.post(BASE, json=good))
check("create returns 201", r.status_code == 201)
fid = r.json().get("id")
check("default status is 'scheduled'", r.json().get("status") == "scheduled")
check("created_at == updated_at on create", r.json()["created_at"] == r.json()["updated_at"])

r = show("GET all", requests.get(BASE))
check("list contains created fixture", any(f["id"] == fid for f in r.json()))

r = show("GET one", requests.get(f"{BASE}/{fid}"))
check("get by id returns 200", r.status_code == 200)

upd = {**good, "status": "completed", "description": "Final: 3-1"}
r = show("PUT update", requests.put(f"{BASE}/{fid}", json=upd))
check("update returns 200 + new status", r.status_code == 200 and r.json()["status"] == "completed")
check("updated_at advanced", r.json()["updated_at"] > r.json()["created_at"])

# ---- failure paths
show_cases = [
    ("POST missing required fixture_name", {k: v for k, v in good.items() if k != "fixture_name"}, 422),
    ("POST name too long (101 chars)", {**good, "fixture_name": "x" * 101}, 422),
    ("POST invalid category enum", {**good, "category": "Curling"}, 422),
    ("POST invalid status enum", {**good, "status": "postponed"}, 422),
    ("POST bad date format", {**good, "match_date": "next tuesday"}, 422),
    ("POST wrong type (name is a number)", {**good, "fixture_name": 12345}, 422),
    ("POST unknown extra field", {**good, "venue": "Field 3"}, 422),
]
for label, payload, want in show_cases:
    r = show(label, requests.post(BASE, json=payload))
    check(f"{label} -> {want}", r.status_code == want)

r = show("POST malformed JSON", requests.post(BASE, data="{not json", headers={"Content-Type": "application/json"}))
check("malformed JSON -> 422", r.status_code == 422)
r = show("GET unknown id (valid ObjectId)", requests.get(f"{BASE}/000000000000000000000000"))
check("unknown id -> 404", r.status_code == 404)
r = show("GET malformed id", requests.get(f"{BASE}/not-an-id"))
check("malformed id -> 400", r.status_code == 400)
r = show("PUT unknown id", requests.put(f"{BASE}/000000000000000000000000", json=good))
check("PUT unknown id -> 404", r.status_code == 404)
r = show("PUT invalid body", requests.put(f"{BASE}/{fid}", json={**good, "category": "Golf"}))
check("PUT invalid enum -> 422", r.status_code == 422)

# ---- direct DB check, bypassing the API
col = MongoClient("mongodb://localhost:27017", tz_aware=True)["s9871_doc"]["fixtures"]
from bson import ObjectId
raw = col.find_one({"_id": ObjectId(fid)})
print("\n### Direct MongoDB document (bypassing API)\n", raw)
check("DB doc persisted with updated status", raw and raw["status"] == "completed")
check("DB stores match_date as BSON date", isinstance(raw["match_date"], datetime))
try:
    col.insert_one({"fixture_name": "x" * 101, "status": "scheduled", "category": "Soccer",
                    "match_date": datetime.now(), "created_at": datetime.now(), "updated_at": datetime.now()})
    check("DB validator rejects 101-char name", False)
except Exception as exc:
    print("direct insert rejected:", type(exc).__name__)
    check("DB validator rejects 101-char name", True)

r = show("DELETE", requests.delete(f"{BASE}/{fid}"))
check("delete returns 204", r.status_code == 204)
r = show("GET after delete", requests.get(f"{BASE}/{fid}"))
check("get after delete -> 404", r.status_code == 404)
r = show("DELETE again", requests.delete(f"{BASE}/{fid}"))
check("second delete -> 404", r.status_code == 404)
check("DB doc really gone", col.find_one({"_id": ObjectId(fid)}) is None)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
