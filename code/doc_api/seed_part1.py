"""Seed a few sample fixtures through the real API (for Compass/mongosh screenshots)."""
import requests

BASE = "http://127.0.0.1:8871/api/fixtures"
SAMPLES = [
    ("Milpitas Lions vs San Jose Tigers", "Season opener, 7-a-side", "Soccer", "scheduled", "2026-11-01T18:00:00Z"),
    ("Fremont Hawks vs Santa Clara Bulls", "Indoor league, 4 x 10 min quarters", "Basketball", "in_progress", "2026-10-15T19:30:00Z"),
    ("Sunnyvale Spikers vs Cupertino Waves", None, "Volleyball", "completed", "2026-10-05T10:00:00Z"),
    ("Bay Area Strikers vs Peninsula XI", "T20 friendly, rain date Nov 9", "Cricket", "scheduled", "2026-11-08T09:00:00Z"),
    ("Palo Alto Rovers vs Mountain View FC", "Cancelled - field closed", "Soccer", "cancelled", "2026-10-20T17:00:00Z"),
]
for name, desc, cat, status, when in SAMPLES:
    body = {"fixture_name": name, "category": cat, "status": status, "match_date": when}
    if desc:
        body["description"] = desc
    r = requests.post(BASE, json=body)
    print(r.status_code, name)
