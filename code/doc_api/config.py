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

# ---- HW6 Part 2: memory settings (mutable at runtime via PUT /api/settings,
# so the Part 3 sweeps can change SHORT_TERM_N without restarting the server).
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

settings = {
    "SHORT_TERM_N": int(os.environ.get("SHORT_TERM_N", "12")),
    "SUMMARIZE_EVERY_USER_MSGS": int(os.environ.get("SUMMARIZE_EVERY_USER_MSGS", "6")),
    "EPISODE_TOP_K": int(os.environ.get("EPISODE_TOP_K", "3")),
    "LIFETIME_EVERY_N_SESSION_SUMMARIES": 2,
    "MAX_FACTS_PER_MESSAGE": 3,
}
