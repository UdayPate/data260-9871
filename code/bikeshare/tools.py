"""
DATA-260 Homework 7 - Part 4: the three MRKL tools for the bike-share membership agent.

Each tool is a plain Python function with a JSON schema, and every one returns the same envelope:
    {"success": bool, "data": ..., "error": "...", "source": "...", "ts": "..."}      (absent keys are left out)

  csv_sql          read-only SELECT over the uploaded trips CSV (in-memory SQLite, authorizer allows only reads)
  policy_retriever fetch a pricing page, save the exact text snapshot (+ SHA-256), return short quotable snippets
  calculator       whitelisted arithmetic, evaluated by walking the AST (no eval)
"""

import ast
import csv
import hashlib
import html as html_lib
import ipaddress
import json
import math
import re
import socket
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

MAX_ROWS = 200
MAX_PAGE_BYTES = 2_000_000
CALC_PATTERN = r"^[0-9+\-*/().\s]+$"

SCHEMAS = {
    "csv_sql": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "One read-only SELECT (or WITH ... SELECT) over the table trips."}},
        "required": ["sql"], "additionalProperties": False},
    "policy_retriever": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The pricing page URL (https)."},
                       "query": {"type": "string", "description": "What to look for, e.g. 'monthly membership price and included minutes'."},
                       "k": {"type": "integer", "minimum": 1, "maximum": 8, "description": "How many snippets to return (default 4)."}},
        "required": ["url", "query"], "additionalProperties": False},
    "calculator": {
        "type": "object",
        "properties": {"expression": {"type": "string", "pattern": CALC_PATTERN, "description": "Arithmetic using only digits, + - * / ( ) . and spaces."},
                       "units": {"type": "string", "description": "Optional unit label for the result, e.g. USD."}},
        "required": ["expression"], "additionalProperties": False},
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ok(data, source: str | None = None) -> dict:
    out = {"success": True, "data": data, "ts": _now()}
    if source:
        out["source"] = source
    return out


def fail(error: str, source: str | None = None) -> dict:
    out = {"success": False, "error": error, "ts": _now()}
    if source:
        out["source"] = source
    return out


# --------------------------------------------------------------------------- csv_sql
_READ_ONLY_OPS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _read_only_authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _READ_ONLY_OPS else sqlite3.SQLITE_DENY


def _parse_ts(value: str):
    try:
        return datetime.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        return None


class CsvSql:
    """The uploaded trips CSV as one SQLite table named trips. Extra column: duration_min = (ended_at - started_at) in minutes
    (NULL when either timestamp is missing or unreadable). All other columns are the CSV's own, as text."""

    def __init__(self, csv_path: Path, display_name: str = "uploaded.csv"):
        self.display_name = display_name
        with open(csv_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self.columns = list(reader.fieldnames or []) + ["duration_min"]
            rows = list(reader)
        self.row_count = len(rows)
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        cols = ", ".join(f'"{c}" REAL' if c == "duration_min" else f'"{c}" TEXT' for c in self.columns)
        self.conn.execute(f"CREATE TABLE trips ({cols})")
        self.null_duration = 0
        batch = []
        for r in rows:
            a, b = _parse_ts(r.get("started_at", "")), _parse_ts(r.get("ended_at", ""))
            dur = round((b - a).total_seconds() / 60, 6) if a and b else None
            self.null_duration += dur is None
            batch.append([r.get(c) for c in self.columns[:-1]] + [dur])
        self.conn.executemany(f"INSERT INTO trips VALUES ({','.join('?' * len(self.columns))})", batch)
        self.conn.commit()
        self.conn.set_authorizer(_read_only_authorizer)   # from here on: reads only
        self.conn.set_progress_handler(self._budget, 1000)
        self._ops = 0

    def _budget(self):
        self._ops += 1
        return 1 if self._ops > 20_000 else 0          # abort a runaway query (~20M VM steps)

    def describe(self) -> str:
        return (f"Table trips ({self.row_count} rows) with columns: {', '.join(self.columns)}. started_at/ended_at are 'YYYY-MM-DD HH:MM:SS.fff' text "
                f"(SQLite strftime works on them); duration_min is the ride length in minutes; rideable_type is classic_bike or electric_bike; "
                f"member_casual is member or casual.")

    def run(self, sql: str) -> dict:
        text = (sql or "").strip().rstrip(";").strip()
        if not text:
            return fail("sql is empty", self.display_name)
        if ";" in text:
            return fail("only one statement is allowed", self.display_name)
        if not re.match(r"(?is)^(select|with)\b", text):
            return fail("only read-only SELECT queries are allowed", self.display_name)
        self._ops = 0
        try:
            cur = self.conn.execute(text)
            fetched = cur.fetchmany(MAX_ROWS + 1)
            names = [d[0] for d in cur.description or []]
        except sqlite3.Error as e:
            return fail(f"SQL error: {e}", self.display_name)
        rows = [dict(zip(names, r)) for r in fetched[:MAX_ROWS]]
        data = {"rows": rows, "row_count": len(rows), "source": self.display_name}
        if len(fetched) > MAX_ROWS:
            data["truncated"] = f"only the first {MAX_ROWS} rows are returned; aggregate in SQL instead"
        return ok(data, self.display_name)


# --------------------------------------------------------------------------- calculator
_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}


def _walk(node):
    if isinstance(node, ast.Expression):
        return _walk(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_walk(node.left), _walk(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _walk(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    raise ValueError("unsupported syntax (only + - * / and parentheses)")


def calculator(expression: str, units: str | None = None) -> dict:
    expr = expression if isinstance(expression, str) else ""
    if not expr.strip():
        return fail("expression is empty")
    if len(expr) > 200:
        return fail("expression is too long (200 characters max)")
    if not re.match(CALC_PATTERN, expr):
        return fail("expression may only contain digits, + - * / ( ) . and spaces")
    try:
        value = _walk(ast.parse(expr.strip(), mode="eval"))
    except ZeroDivisionError:
        return fail("division by zero")
    except (SyntaxError, ValueError, RecursionError) as e:
        return fail(f"could not evaluate: {e}")
    if not math.isfinite(value):
        return fail("result is not a finite number")
    data = {"value": float(value)}
    if units:
        data["units"] = units
    return ok(data)


# --------------------------------------------------------------------------- policy_retriever
def extract_text(page_html: str) -> list[str]:
    """Visible text of an HTML page, one entry per text node, in document order."""
    page = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", page_html)
    page = re.sub(r"(?s)<!--.*?-->", " ", page)
    lines = [" ".join(html_lib.unescape(t).split()) for t in re.sub(r"<[^>]+>", "\n", page).split("\n")]
    return [ln for ln in lines if ln]


_PRICE_TAG = re.compile(r"^\$\d+(\.\d\d)?(/\w+)?$")
_PRICE_ROW_HEADING = re.compile(r"(?i)^(classic|ebike|e-bike)( bike)? prices?$")


def annotate_columns(lines: list[str]) -> list[str]:
    """Comparison tables flatten to text with the plan names lost: a row of N values is just N lines in column order. Find the
    headline price tags (the first run of 3+ consecutive bare prices, e.g. $1.00 / $15/day / $29/month ...) and tag each value line under a
    'Classic bike prices' / 'Ebike prices' heading with its column's tag, as '[column: $29/month]'. The saved snapshot is NOT changed."""
    tags = []
    for i in range(len(lines) - 2):
        if all(_PRICE_TAG.match(x) for x in lines[i: i + 3]):
            j = i
            while j < len(lines) and _PRICE_TAG.match(lines[j]):
                tags.append(lines[j])
                j += 1
            break
    if len(tags) < 3:
        return lines
    out = list(lines)
    for i, line in enumerate(lines):
        if _PRICE_ROW_HEADING.match(line):
            values = lines[i + 1: i + 1 + len(tags)]
            if len(values) == len(tags) and all(re.search(r"\$|free", v, re.I) for v in values):
                for k, tag in enumerate(tags):
                    out[i + 1 + k] = f"{values[k]} [column: {tag}]"
    return out


def make_passages(lines: list[str], window: int = 6, stride: int = 2) -> list[str]:
    """Overlapping windows of consecutive (column-annotated) lines, identical windows removed (pricing pages repeat their tables)."""
    raw_len = len(lines)
    lines = annotate_columns(lines)
    seen, out = set(), []
    # one passage per price row: the heading plus all its (tagged) values, so a whole row is retrievable as one quotable snippet
    rows = [i for i, ln in enumerate(lines[:raw_len]) if _PRICE_ROW_HEADING.match(ln)]
    for i in rows:
        j = i + 1
        while j < raw_len and "[column:" in lines[j]:
            j += 1
        text = " | ".join(lines[i:j])
        if j > i + 1 and text not in seen:
            seen.add(text)
            out.append(text[:700])
    for i in range(0, max(len(lines) - 1, 1), stride):
        text = " | ".join(lines[i: i + window])
        if text not in seen and len(text) > 25:
            seen.add(text)
            out.append(text[:520])
    return out


def _public_https(url: str) -> str | None:
    """Return an error message unless the URL is https to a public host (no localhost / private ranges)."""
    p = urllib.parse.urlparse(url or "")
    if p.scheme != "https" or not p.hostname:
        return "only https URLs are allowed"
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return "that host resolves to a private or local address"
    except (socket.gaierror, ValueError):
        return "could not resolve the host"
    return None


def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DATA-260 coursework; bikeshare agent)"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read(MAX_PAGE_BYTES + 1)
    if len(raw) > MAX_PAGE_BYTES:
        raise ValueError("page is larger than 2 MB")
    return raw.decode("utf-8", errors="replace")


_EMBEDDER = None


def default_embedder():
    """all-MiniLM-L6-v2 (the embedding model used in HW4 and HW6), loaded once per process. Tries the local cache first: going to the
    network just to check for updates cost about 75 s on the first call."""
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer

        name = "sentence-transformers/all-MiniLM-L6-v2"
        try:
            model = SentenceTransformer(name, local_files_only=True)
        except Exception:
            model = SentenceTransformer(name)
        _EMBEDDER = lambda xs: model.encode(xs, normalize_embeddings=True)  # noqa: E731
    return _EMBEDDER


class PolicyRetriever:
    """One instance per agent run. The first call fetches the page and freezes it: the extracted text is written to
    `snapshot_dir/<run_id>_pricing.txt` with a metadata file (url, access time, SHA-256 of the text), and every later call in
    the run searches that frozen text, so the evidence cannot change mid-run or afterwards."""

    def __init__(self, snapshot_dir: Path, run_id: str, fetcher=fetch_page, embedder=None, check_url: bool = True):
        self.snapshot_dir, self.run_id, self.fetcher, self.check_url = Path(snapshot_dir), run_id, fetcher, check_url
        self._embedder = embedder
        self.snapshot: dict | None = None
        self._passages: list[str] = []
        self._vectors = None

    def _embed(self, texts: list[str]):
        if self._embedder is None:
            self._embedder = default_embedder()
        return self._embedder(texts)

    def _load(self, url: str):
        if self.check_url:
            problem = _public_https(url)
            if problem:
                raise ValueError(problem)
        page = self.fetcher(url)
        lines = extract_text(page)
        text = "\n".join(lines) + "\n"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_dir / f"{self.run_id}_pricing.txt"
        path.write_bytes(text.encode("utf-8"))
        self.snapshot = {"url": url, "accessed_at": _now(), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                         "html_sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(), "text_bytes": len(text.encode("utf-8")),
                         "text_lines": len(lines), "path": str(path)}
        (self.snapshot_dir / f"{self.run_id}_pricing.meta.json").write_text(json.dumps(self.snapshot, indent=2), encoding="utf-8", newline="\n")
        self._passages = make_passages(lines)
        self._vectors = self._embed(self._passages)

    def run(self, url: str, query: str, k: int = 4) -> dict:
        if not (query or "").strip():
            return fail("query is empty", url)
        try:
            if self.snapshot is None:
                self._load(url)
            elif url != self.snapshot["url"]:
                return fail(f"this run is bound to {self.snapshot['url']}; it cannot fetch another URL", url)
        except (ValueError, OSError) as e:
            return fail(f"could not fetch the pricing page: {e}", url)
        if not self._passages:
            return fail("the page contained no readable text", url)
        import numpy as np

        qv = np.asarray(self._embed([query]))[0]
        scores = np.asarray(self._vectors) @ qv
        order = np.argsort(-scores)[: max(1, min(int(k), 8))]
        return ok({"passages": [{"text": self._passages[i], "source": url, "score": round(float(scores[i]), 4)} for i in order]}, url)
