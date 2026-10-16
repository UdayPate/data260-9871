"""
DATA-260 Homework 6: FastAPI app on PORT_BASE (8871).
Part 1 mounts the fixtures CRUD router; later parts add chat/memory routers.
Run from this folder:  python main.py
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import PyMongoError

import config
import db
import chat_routes
import routes

log = logging.getLogger("doc_api")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Community Sports League Fixtures - Document API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Clear, flat validation errors: [{field, message}] with HTTP 422."""
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body") or "body",
         "message": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "validation failed", "errors": errors})


@app.exception_handler(PyMongoError)
async def mongo_handler(request: Request, exc: PyMongoError):
    log.exception("database error")
    return JSONResponse(status_code=503, content={"detail": "database unavailable or failed"})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/api/health")
def health():
    db.get_client().admin.command("ping")
    return {"status": "ok", "db": config.MONGO_DB}


@app.get("/chat", include_in_schema=False)
def chat_page():
    """Optional mini chat UI for Part 2 (calls POST /api/chat on the same origin)."""
    return FileResponse(Path(__file__).resolve().parent / "static" / "chat.html")


app.include_router(routes.router)
app.include_router(chat_routes.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=config.PORT_BASE)
