"""
DATA-260 Homework 6 - Part 2: /api/chat, /api/memory/{user_id},
/api/aggregate/{user_id}, plus a small runtime /api/settings endpoint
(used by the Part 3 SHORT_TERM_N sweeps).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import config
import db
import llm
import memory

router = APIRouter(tags=["chat"])

USER_ID_PATTERN = r"^[A-Za-z0-9_.@-]{1,64}$"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(..., pattern=USER_ID_PATTERN)
    session_id: str | None = Field(None, min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    SHORT_TERM_N: int | None = Field(None, ge=0, le=200)
    SUMMARIZE_EVERY_USER_MSGS: int | None = Field(None, ge=0, le=200)
    EPISODE_TOP_K: int | None = Field(None, ge=0, le=20)


def _iso(doc: dict, *keys) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in doc.items() if k in keys}


@router.post("/api/chat")
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    s = config.settings

    saved = memory.save_message(req.user_id, session_id, "user", req.message)
    window = memory.short_term_window(req.user_id, session_id, s["SHORT_TERM_N"],
                                      before_id=saved["_id"])
    sess = memory.latest_summary(req.user_id, "session", session_id)
    life = memory.latest_summary(req.user_id, "user")
    episodes = memory.retrieve_episodes(req.user_id, req.message, s["EPISODE_TOP_K"])

    messages, parts = memory.build_prompt(
        window, sess["text"] if sess else None, life["text"] if life else None,
        episodes, req.message)
    try:
        result = llm.complete(messages)
        reply = result["text"] or "(the model returned an empty reply)"
        memory.save_message(req.user_id, session_id, "assistant", reply)
        new_facts = memory.extract_and_store_episodes(req.user_id, session_id, req.message)
        summaries = memory.maybe_summarize(req.user_id, session_id)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "reply": reply,
        "user_id": req.user_id,
        "session_id": session_id,
        "memory_used": {
            "short_term_count": len(window),
            "short_term_messages": [{"role": m["role"], "content": m["content"]} for m in window],
            "session_summary": sess["text"] if sess else None,
            "long_term_summary": life["text"] if life else None,
            "episodic_facts": episodes,
        },
        "memory_written": {
            "new_episodes": new_facts,
            "session_summary_created": summaries["session_summary"] is not None,
            "lifetime_summary_created": summaries["lifetime_summary"] is not None,
        },
        "usage": {
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "latency_ms": result["latency_ms"],
        },
        "prompt_parts": parts,
    }


@router.get("/api/memory/{user_id}")
def get_memory(user_id: str):
    d = db.get_db()
    msgs = list(d["messages"].find({"user_id": user_id}).sort("_id", -1).limit(16))[::-1]
    eps = list(d["episodes"].find({"user_id": user_id}).sort("_id", -1).limit(20))
    sess = memory.latest_summary(user_id, "session")
    life = memory.latest_summary(user_id, "user")
    if not msgs and not eps and not sess and not life:
        raise HTTPException(status_code=404, detail=f"no memory stored for user '{user_id}'")
    return {
        "user_id": user_id,
        "messages": [_iso(m, "session_id", "role", "content", "created_at") for m in msgs],
        "latest_session_summary": _iso(sess, "session_id", "text", "created_at") if sess else None,
        "latest_lifetime_summary": _iso(life, "text", "created_at") if life else None,
        "episodes": [{**_iso(e, "session_id", "fact", "importance", "created_at"),
                      "embedding_dim": len(e.get("embedding", []))} for e in eps],
    }


@router.get("/api/aggregate/{user_id}")
def aggregate(user_id: str):
    d = db.get_db()
    daily = d["messages"].aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])
    recent = d["summaries"].find({"user_id": user_id}).sort("created_at", -1).limit(5)
    return {
        "user_id": user_id,
        "daily_message_counts": [{"date": r["_id"], "count": r["count"]} for r in daily],
        "recent_summaries": [_iso(s, "scope", "session_id", "text", "created_at") for s in recent],
    }


@router.get("/api/settings")
def get_settings():
    return config.settings


@router.put("/api/settings")
def put_settings(body: SettingsUpdate):
    config.settings.update(body.model_dump(exclude_none=True))
    return config.settings
