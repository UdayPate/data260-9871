"""
DATA-260 Homework 6 - server configuration (shared by all HW6 parts).
Values are fixed per CLAUDE.md; MONGO_URI may be overridden via env var.
"""

import os

SID4 = "9871"
PREFIX = "s9871"
PORT_BASE = 8871
SEED = 9871
VERIFY_SEED = 269871

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = f"{PREFIX}_doc"
FIXTURES_COLLECTION = "fixtures"
CORS_ORIGINS = ["http://localhost:5173", f"http://localhost:{PORT_BASE}"]
