"""
DATA-260 Homework 6 - Part 2: sentence-transformers embeddings (all-MiniLM-L6-v2),
the same embedding model CLAUDE.md lists for retrieval work (HW4 RAG used it).
"""

import threading

import numpy as np

import config

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(config.EMBED_MODEL)
        return _model


def embed(text: str) -> list[float]:
    """Return a unit-length embedding as a plain list of floats (BSON-safe)."""
    vec = _get_model().encode(text, normalize_embeddings=True)
    return [float(x) for x in np.asarray(vec)]


def cosine_top_k(query_vec: list[float], candidates: list[dict], k: int) -> list[dict]:
    """Rank candidate episode docs by cosine similarity to query_vec.
    Vectors are unit length, so cosine == dot product. Adds a `score` key."""
    if not candidates or k <= 0:
        return []
    q = np.asarray(query_vec, dtype=np.float32)
    mat = np.asarray([c["embedding"] for c in candidates], dtype=np.float32)
    denom = (np.linalg.norm(mat, axis=1) * np.linalg.norm(q)) + 1e-9
    scores = (mat @ q) / denom
    order = np.argsort(-scores)[:k]
    return [{**candidates[i], "score": float(scores[i])} for i in order]
