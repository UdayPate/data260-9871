"""
DATA-260 Homework 6 - Part 2: short-term / long-term / episodic memory logic.

Collections (same s9871_doc database, Part 1's `fixtures` is untouched):
  messages  : user_id, session_id, role, content, created_at
  summaries : user_id, session_id (null for lifetime), scope, text, created_at
  episodes  : user_id, session_id, fact, importance, embedding, created_at
"""

import json
import re
from datetime import datetime, timezone

import config
import db
import embeddings
import llm

SYSTEM_PRIMER = (
    "You are a friendly assistant for a community sports league. You help with "
    "fixtures, teams and scheduling questions. Use the remembered context below "
    "when it is relevant, never invent facts about the user, and keep replies "
    "short (1-3 sentences)."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Storage helpers
# --------------------------------------------------------------------------
def save_message(user_id: str, session_id: str, role: str, content: str) -> dict:
    doc = {"user_id": user_id, "session_id": session_id, "role": role,
           "content": content, "created_at": _now()}
    doc["_id"] = db.get_db()["messages"].insert_one(doc).inserted_id
    return doc


def short_term_window(user_id: str, session_id: str, n: int, before_id=None) -> list[dict]:
    """Last n messages of the session, oldest first. `before_id` excludes the
    message that was just saved (it is passed to the model separately)."""
    query = {"user_id": user_id, "session_id": session_id}
    if before_id is not None:
        query["_id"] = {"$lt": before_id}
    docs = list(db.get_db()["messages"].find(query).sort("_id", -1).limit(max(n, 0)))
    return list(reversed(docs))


def latest_summary(user_id: str, scope: str, session_id: str | None = None) -> dict | None:
    query = {"user_id": user_id, "scope": scope}
    if scope == "session" and session_id is not None:
        query["session_id"] = session_id
    return db.get_db()["summaries"].find_one(query, sort=[("created_at", -1), ("_id", -1)])


def count_user_messages(user_id: str, session_id: str) -> int:
    return db.get_db()["messages"].count_documents(
        {"user_id": user_id, "session_id": session_id, "role": "user"})


# --------------------------------------------------------------------------
# Episodic memory: extraction + embedding + retrieval
# --------------------------------------------------------------------------
_EXTRACT_PROMPT = (
    "Extract up to {max_facts} short, durable facts about the USER from the message "
    "below (preferences, their own team, schedules, constraints, personal details). "
    "Rules: 'we/our/my team' refers to the user's own team; a team the user calls a "
    "rival or opponent is NOT the user's team - state it as 'The user's rival/opponent "
    "is X'. Use only what the message says. Ignore greetings and questions with no "
    "facts. Reply with ONLY a JSON array like "
    '[{{"fact": "short sentence", "importance": 0.0-1.0}}]. Reply [] if there are none.'
    "\n\nMessage: {message}"
)


def clean_bullets(text: str) -> str:
    """Keep only bullet lines (drops model commentary such as a trailing
    '(No additional information...)'); falls back to the raw text."""
    lines = [ln.rstrip() for ln in text.splitlines()
             if ln.strip().startswith(("-", "*", "\u2022"))]
    return "\n".join(lines) if lines else text.strip()


def parse_facts(raw: str, max_facts: int) -> list[dict]:
    """Defensive parse of the model's JSON array; returns [] on anything odd."""
    match = re.search(r"\[.*\]", raw, flags=re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    facts = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        fact = str(it.get("fact", "")).strip()
        try:
            importance = float(it.get("importance", 0.5))
        except (TypeError, ValueError):
            importance = 0.5
        if fact:
            facts.append({"fact": fact[:200], "importance": min(1.0, max(0.0, importance))})
    return facts[:max_facts]


def extract_and_store_episodes(user_id: str, session_id: str, message: str) -> list[dict]:
    res = llm.complete([{"role": "user", "content": _EXTRACT_PROMPT.format(
        max_facts=config.settings["MAX_FACTS_PER_MESSAGE"], message=message)}])
    facts = parse_facts(res["text"], config.settings["MAX_FACTS_PER_MESSAGE"])
    stored = []
    for f in facts:
        doc = {"user_id": user_id, "session_id": session_id, "fact": f["fact"],
               "importance": f["importance"], "embedding": embeddings.embed(f["fact"]),
               "created_at": _now()}
        db.get_db()["episodes"].insert_one(doc)
        stored.append({"fact": doc["fact"], "importance": doc["importance"]})
    return stored


def retrieve_episodes(user_id: str, query_text: str, k: int) -> list[dict]:
    """Top-k stored facts for this user by cosine similarity to the query."""
    candidates = list(db.get_db()["episodes"].find({"user_id": user_id}))
    top = embeddings.cosine_top_k(embeddings.embed(query_text), candidates, k)
    return [{"fact": e["fact"], "importance": e["importance"],
             "score": round(e["score"], 4), "session_id": e["session_id"]} for e in top]


# --------------------------------------------------------------------------
# Long-term memory: session summaries + lifetime summary
# --------------------------------------------------------------------------
def _transcript(msgs: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in msgs)


def maybe_summarize(user_id: str, session_id: str, every: int | None = None) -> dict:
    """Every SUMMARIZE_EVERY_USER_MSGS user messages: write a session summary
    (scope='session'); every LIFETIME_EVERY_N_SESSION_SUMMARIES session summaries,
    condense into the lifetime summary (scope='user', session_id=None)."""
    every = config.effective_memory_params()[1] if every is None else every
    n_user = count_user_messages(user_id, session_id)
    out = {"session_summary": None, "lifetime_summary": None}
    if every <= 0 or n_user == 0 or n_user % every != 0:
        return out

    col = db.get_db()["messages"]
    recent = list(col.find({"user_id": user_id, "session_id": session_id})
                  .sort("_id", -1).limit(every * 2))[::-1]
    prev = latest_summary(user_id, "session", session_id)
    prompt = ("Summarize the conversation below into at most 5 concise bullet points "
              "capturing facts about the user and decisions made. Output ONLY the bullet "
              "list, each line starting with '- ', with no other commentary. "
              + (f"Previous summary (update it: keep facts that are still true AND add every "
                 f"new fact from the conversation below):\n{prev['text']}\n\n" if prev else "")
              + f"Conversation:\n{_transcript(recent)}")
    text = clean_bullets(llm.complete([{"role": "user", "content": prompt}])["text"])
    if not text:
        return out
    db.get_db()["summaries"].insert_one({
        "user_id": user_id, "session_id": session_id, "scope": "session",
        "text": text, "created_at": _now()})
    out["session_summary"] = text

    n_sess = db.get_db()["summaries"].count_documents({"user_id": user_id, "scope": "session"})
    if n_sess % config.settings["LIFETIME_EVERY_N_SESSION_SUMMARIES"] == 0:
        sess = list(db.get_db()["summaries"].find({"user_id": user_id, "scope": "session"})
                    .sort("created_at", -1).limit(4))[::-1]
        old = latest_summary(user_id, "user")
        prompt = ("Merge these notes about one user into at most 6 concise bullet points. "
                  "Keep durable facts, drop one-off details, and prefer the newest "
                  "information if two notes conflict. Output ONLY the bullet list, each line "
                  "starting with '- ', with no other commentary.\n\n"
                  + (f"Existing lifetime summary:\n{old['text']}\n\n" if old else "")
                  + "Session summaries:\n" + "\n---\n".join(s["text"] for s in sess))
        life = clean_bullets(llm.complete([{"role": "user", "content": prompt}])["text"])
        if life:
            db.get_db()["summaries"].insert_one({
                "user_id": user_id, "session_id": None, "scope": "user",
                "text": life, "created_at": _now()})
            out["lifetime_summary"] = life
    return out


# --------------------------------------------------------------------------
# Prompt assembly
# --------------------------------------------------------------------------
def build_prompt(window: list[dict], session_summary: str | None,
                 lifetime_summary: str | None, episodes: list[dict],
                 message: str) -> tuple[list[dict], dict]:
    """Order: system primer + long-term summaries, short-term window, current
    message, episodic facts. Returns (messages, parts) - `parts` keeps each
    component's text separate so Part 3 can attribute tokens per component."""
    long_term = ""
    if lifetime_summary:
        long_term += f"\n\nLifetime summary of this user:\n{lifetime_summary}"
    if session_summary:
        long_term += f"\n\nSummary of this session so far:\n{session_summary}"
    episodic = ""
    if episodes:
        episodic = ("\n\nRelevant remembered facts about the user:\n"
                    + "\n".join(f"- {e['fact']}" for e in episodes))

    messages = [{"role": "system", "content": SYSTEM_PRIMER + long_term}]
    messages += [{"role": m["role"], "content": m["content"]} for m in window]
    messages.append({"role": "user", "content": message + episodic})
    parts = {
        "system_primer": SYSTEM_PRIMER,
        "long_term_summary": long_term.strip(),
        "short_term_window": "\n".join(f"{m['role']}: {m['content']}" for m in window),
        "episodic_facts": episodic.strip(),
        "current_message": message,
    }
    return messages, parts
