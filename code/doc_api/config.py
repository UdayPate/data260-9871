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
TOKENIZER_NAME = "Qwen/Qwen3-8B"  # exact tokenizer family of qwen3:8b, used for per-component counts
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

settings = {
    "SHORT_TERM_N": int(os.environ.get("SHORT_TERM_N", "12")),
    "SUMMARIZE_EVERY_USER_MSGS": int(os.environ.get("SUMMARIZE_EVERY_USER_MSGS", "6")),
    "EPISODE_TOP_K": int(os.environ.get("EPISODE_TOP_K", "3")),
    "LIFETIME_EVERY_N_SESSION_SUMMARIES": 2,
    "MAX_FACTS_PER_MESSAGE": 3,
    # Part 3 memory-saving policy: "none" (plain sliding window of SHORT_TERM_N)
    # or "compress" (keep only the last COMPRESS_KEEP_LAST raw messages; older
    # turns live only in a session summary refreshed every COMPRESS_SUMMARY_EVERY
    # user messages).
    "LLM_SEED": SEED,  # Ollama sampling seed; Part 3 repeats use SEED, SEED+1, SEED+2
    "POLICY": "none",
    "COMPRESS_KEEP_LAST": 6,
    "COMPRESS_SUMMARY_EVERY": 3,
}


def effective_memory_params() -> tuple[int, int]:
    """(window size, summarize-every) after applying the active policy."""
    if settings["POLICY"] == "compress":
        return settings["COMPRESS_KEEP_LAST"], settings["COMPRESS_SUMMARY_EVERY"]
    return settings["SHORT_TERM_N"], settings["SUMMARIZE_EVERY_USER_MSGS"]

# ---- HW6 Part 4: file-based memory (AGENT.md + MEMORY.md at the repo root)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_PATH = os.environ.get("AGENT_PATH", os.path.join(_REPO_ROOT, "AGENT.md"))
MEMORY_PATH = os.environ.get("FILE_MEMORY_PATH", os.path.join(_REPO_ROOT, "MEMORY.md"))
MEMORY_BACKUP_DIR = os.environ.get(
    "FILE_MEMORY_BACKUP_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".memory_backups"))
MEMORY_MAX_LINES = 40      # consolidate when MEMORY.md has MORE than this many entries ...
MEMORY_MAX_AGE_HOURS = 24  # ... or its last-consolidated time is older than this
