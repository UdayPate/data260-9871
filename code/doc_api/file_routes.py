"""
DATA-260 Homework 6 - Part 4: HTTP access to the file-based memory system.
POST /api/file-chat  {"message": "..."}  - a normal turn or a /command
GET  /api/file-memory                    - raw state (counts, timestamp, consolidation status)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import file_memory
import llm

router = APIRouter(tags=["file-memory"])


class FileChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=4000)


@router.post("/api/file-chat")
def file_chat(req: FileChatRequest):
    try:
        return file_memory.chat_turn(req.message)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/file-memory")
def file_memory_state():
    mem = file_memory.load_memory()
    needed, why = file_memory.consolidation_needed(mem)
    ts = file_memory.read_last_consolidated(mem)
    return {"entries": len(file_memory.entry_lines(mem)),
            "last_consolidated": ts.isoformat() if ts else None,
            "consolidation_needed": needed, "reason": why,
            "agent_md_lines": len(file_memory.entry_lines(file_memory.load_agent()))}
