"""
DATA-260 Homework 7 - Part 4: a small FastAPI server and one page for the bike-share membership agent.

  GET  /                  the UI (static/index.html)
  POST /api/run           multipart: csv (file) + pricing_url  -> {run_id}; the agent runs in a background thread
  GET  /api/runs/{id}     {status, events (the live timeline), result (when done)}

One run at a time (one local model): a second POST while a run is active gets 409. Uploads are limited to 5 MB and must be a CSV with the
columns the tools need. Every finished run is written to reports/hw07/raw/part4_runs/<run_id>.json.

Run from the repo root, inside the venv:   python code/bikeshare/server.py        (serves on PORT_BASE + 1 = 8872)
"""

import csv
import io
import json
import sys
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import REPO_ROOT, run_bike_agent  # noqa: E402

PORT = 8872
MAX_UPLOAD = 5_000_000
REQUIRED = {"rideable_type", "started_at", "ended_at"}
UPLOADS = REPO_ROOT / "reports" / "hw07" / "part4" / "uploads"
RUNS_DIR = REPO_ROOT / "reports" / "hw07" / "raw" / "part4_runs"

app = FastAPI(title="Bay Wheels membership agent")
runs: dict[str, dict] = {}
_busy = threading.Lock()


@app.get("/")
def index():
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html")


def _worker(run_id: str, csv_path: Path, url: str, display_name: str):
    def on_event(event):
        runs[run_id]["events"].append(event)

    try:
        result = run_bike_agent(csv_path, url, run_id=run_id, display_name=display_name, on_event=on_event)
    except Exception as e:                                   # never leave the page waiting forever
        result = {"run_id": run_id, "stop_reason": "error", "error": f"{type(e).__name__}: {e}", "result": None, "timeline": runs[run_id]["events"]}
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    runs[run_id].update(status="done", result=result)
    _busy.release()


@app.post("/api/run")
async def start_run(csv_file: UploadFile = File(..., alias="csv"), pricing_url: str = Form(...)):
    name = csv_file.filename or "uploaded.csv"
    if not name.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file.")
    raw = await csv_file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "The CSV is larger than 5 MB.")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        missing = REQUIRED - set(reader.fieldnames or [])
        rows = sum(1 for _ in reader)
    except (UnicodeDecodeError, csv.Error):
        raise HTTPException(400, "The file is not a readable UTF-8 CSV.")
    if missing:
        raise HTTPException(400, f"The CSV is missing required columns: {', '.join(sorted(missing))}.")
    if rows == 0:
        raise HTTPException(400, "The CSV has no trip rows.")
    if not pricing_url.strip().lower().startswith("https://"):
        raise HTTPException(400, "The pricing URL must start with https://")
    if not _busy.acquire(blocking=False):
        raise HTTPException(409, "A run is already in progress. Wait for it to finish.")
    run_id = uuid.uuid4().hex[:10]
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{run_id}.csv"
    path.write_text(text, encoding="utf-8", newline="\n")
    runs[run_id] = {"status": "running", "events": [], "result": None, "rows": rows}
    threading.Thread(target=_worker, args=(run_id, path, pricing_url.strip(), name), daemon=True).start()
    return {"run_id": run_id, "rows": rows}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run id.")
    return run


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
