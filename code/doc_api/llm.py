"""
DATA-260 Homework 6 - Part 2: thin wrapper over the HW1 model adapter.
Every model call goes through src/model_client.py's ModelClient (CLAUDE.md /
HW1 rule). This wrapper adds: a lock (one Ollama model, one call at a time),
per-call token + latency measurement, and a reset of the adapter's in-memory
history so a long-running server doesn't grow it without bound.
"""

import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from model_client import ModelClient  # noqa: E402

import config  # noqa: E402

_lock = threading.Lock()
_client = None


class LLMError(RuntimeError):
    """Raised when the local model cannot be reached or fails."""


def _get_client() -> ModelClient:
    global _client
    if _client is None:
        _client = ModelClient(model=config.LLM_MODEL, temperature=0.3, reasoning=False)
    return _client


def complete(messages: list[dict]) -> dict:
    """Run one completion. Returns {text, prompt_tokens, completion_tokens, latency_ms}."""
    with _lock:
        client = _get_client()
        client.history = []
        before_in, before_out = client.cumulative_input_tokens, client.cumulative_output_tokens
        t0 = time.perf_counter()
        try:
            text = client.complete(messages)
        except Exception as exc:  # connection refused, model missing, ...
            raise LLMError(f"model call failed: {exc}") from exc
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "text": (text or "").strip(),
            "prompt_tokens": client.cumulative_input_tokens - before_in,
            "completion_tokens": client.cumulative_output_tokens - before_out,
            "latency_ms": round(latency_ms, 1),
        }
