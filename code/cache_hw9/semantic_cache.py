"""
DATA-260 Homework 9 - Part 2: semantic response cache in Redis (vector index, cosine similarity).

Each entry is a Redis hash `s9871:semcache:<id>` with: query, embedding (384 x float32 bytes, L2-normalised MiniLM), answer, status,
version (the data-version marker, see facts.py), refs (fixture codes the answer depends on) and created_at. A RediSearch FLAT index
`s9871:idx:semcache` over `embedding` (DISTANCE_METRIC COSINE) answers "nearest cached query": Redis returns the cosine DISTANCE
d = 1 - cos, so similarity = 1 - d. FLAT is an exact scan, which is the right choice at this size and keeps results reproducible.
"""

import json
import time
import uuid
from datetime import datetime

import numpy as np
import redis
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

PREFIX = "s9871"
INDEX = f"{PREFIX}:idx:semcache"
KEY_PREFIX = f"{PREFIX}:semcache:"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384
_model = None


def embed(text: str) -> np.ndarray:
    """Unit-length float32 embedding; the model is loaded once per process (local cache first, as in HW7)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        try:
            _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:  # noqa: BLE001 - not in the local cache yet: download once
            _model = SentenceTransformer(MODEL_NAME)
    return np.asarray(_model.encode(text, normalize_embeddings=True), dtype=np.float32)


class SemanticCache:
    def __init__(self, redis_client=None):
        self.r = redis_client or redis.Redis(host="localhost", port=6379, decode_responses=True)
        self.ensure_index()

    def ensure_index(self) -> None:
        try:
            self.r.ft(INDEX).info()
        except redis.exceptions.ResponseError:
            schema = (TextField("query"), VectorField("embedding", "FLAT", {"TYPE": "FLOAT32", "DIM": DIM, "DISTANCE_METRIC": "COSINE"}))
            self.r.ft(INDEX).create_index(schema, definition=IndexDefinition(prefix=[KEY_PREFIX], index_type=IndexType.HASH))

    def clear(self) -> None:
        """Drop the index with its documents, then recreate it empty."""
        try:
            self.r.ft(INDEX).dropindex(delete_documents=True)
        except redis.exceptions.ResponseError:
            pass
        for key in self.r.scan_iter(f"{KEY_PREFIX}*"):
            self.r.delete(key)
        self.ensure_index()

    def size(self) -> int:
        return int(self.r.ft(INDEX).info()["num_docs"])

    def nearest(self, vector: np.ndarray):
        """Best cached entry for the vector: {key, similarity, query, answer, version, refs, status}, or None when the cache is empty."""
        q = (Query("*=>[KNN 1 @embedding $vec AS dist]").sort_by("dist")
             .return_fields("query", "answer", "version", "refs", "status", "dist").dialect(2))
        docs = self.r.ft(INDEX).search(q, query_params={"vec": vector.tobytes()}).docs
        if not docs:
            return None
        d = docs[0]
        return {"key": d.id, "similarity": round(1.0 - float(d.dist), 4), "query": d.query, "answer": d.answer,
                "version": d.version, "refs": json.loads(d.refs), "status": d.status}

    def store(self, query: str, vector: np.ndarray, answer: str, version: str, refs: list[str], status: str = "approved") -> str:
        key = f"{KEY_PREFIX}{uuid.uuid4().hex[:12]}"
        self.r.hset(key, mapping={"query": query, "embedding": vector.tobytes(), "answer": answer, "status": status,
                                  "version": version, "refs": json.dumps(refs), "created_at": datetime.now().isoformat(timespec="seconds")})
        return key

    def delete(self, key: str) -> None:
        self.r.delete(key)


def now_ms() -> float:
    return time.perf_counter() * 1000
