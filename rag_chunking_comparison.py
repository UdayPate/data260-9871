import csv
import json
import time
from pathlib import Path

import numpy as np
import yaml

from llama_index.core import Document, VectorStoreIndex, StorageContext
from llama_index.core.node_parser import (
    TokenTextSplitter,
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
)
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# ---------------------------------------------------------------------
# Paths and config
# ---------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = REPO_ROOT / "reports" / "hw03" / "corpus"
QUESTIONS_FILE = REPO_ROOT / "reports" / "hw03" / "questions.yaml"
RAW_DIR = REPO_ROOT / "reports" / "hw03" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 3

# Chunking parameters - chosen deliberately, documented here:
TOKEN_CHUNK_SIZE = 256      # a few paragraphs' worth per chunk
TOKEN_CHUNK_OVERLAP = 20    # small overlap so boundary context isn't lost
SEMANTIC_BUFFER_SIZE = 1    # sentence-level buffer window for boundary detection
SENTENCE_WINDOW_SIZE = 3    # 3 sentences of context on each side


# ---------------------------------------------------------------------
# Load corpus and questions
# ---------------------------------------------------------------------

def load_documents():
    documents = []
    for txt_file in sorted(CORPUS_DIR.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        documents.append(Document(text=text, metadata={"source_file": txt_file.name}))
    return documents


def load_questions():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["questions"]


# ---------------------------------------------------------------------
# Build an index per technique
# ---------------------------------------------------------------------

def build_index(nodes, embed_model):
    """Builds an in-memory VectorStoreIndex (SimpleVectorStore) over the
    given nodes, using the shared embedding model."""
    vector_store = SimpleVectorStore()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex(
        nodes, storage_context=storage_context, embed_model=embed_model
    )


def build_token_index(documents, embed_model):
    splitter = TokenTextSplitter(
        chunk_size=TOKEN_CHUNK_SIZE, chunk_overlap=TOKEN_CHUNK_OVERLAP
    )
    nodes = splitter.get_nodes_from_documents(documents)
    return build_index(nodes, embed_model), nodes


def build_semantic_index(documents, embed_model):
    splitter = SemanticSplitterNodeParser.from_defaults(
        embed_model=embed_model, buffer_size=SEMANTIC_BUFFER_SIZE
    )
    nodes = splitter.get_nodes_from_documents(documents)
    return build_index(nodes, embed_model), nodes


def build_sentence_window_index(documents, embed_model):
    splitter = SentenceWindowNodeParser.from_defaults(
        window_size=SENTENCE_WINDOW_SIZE
    )
    nodes = splitter.get_nodes_from_documents(documents)
    return build_index(nodes, embed_model), nodes


# ---------------------------------------------------------------------
# Retrieval-only function (shared across all three techniques)
# ---------------------------------------------------------------------

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def retrieve_and_analyze(technique_name, index, embed_model, query, k=TOP_K):
    """Runs retrieval for one query against one technique's index, prints
    and returns a structured result with rank/store_score/cosine_sim/
    chunk_len/preview for each retrieved node."""

    print(f"\n{'='*70}")
    print(f"TECHNIQUE: {technique_name}   QUERY: {query!r}")
    print(f"{'='*70}")

    # Query embedding
    query_embedding = embed_model.get_query_embedding(query)
    query_vec = np.array(query_embedding)
    print(f"Query embedding dimension: {query_vec.shape[0]}")
    print(f"Query embedding first 8 values: {query_vec[:8]}")

    # Retrieve top-k
    retriever = index.as_retriever(similarity_top_k=k)
    start = time.perf_counter()
    results = retriever.retrieve(query)
    latency_ms = (time.perf_counter() - start) * 1000

    # Compute doc embeddings explicitly (for cosine_sim), stack for shape reporting
    doc_vecs = []
    rows = []
    for rank, node_with_score in enumerate(results, start=1):
        chunk_text = node_with_score.node.get_content()
        store_score = node_with_score.score

        doc_embedding = embed_model.get_text_embedding(chunk_text)
        doc_vec = np.array(doc_embedding)
        doc_vecs.append(doc_vec)

        cos_sim = cosine_similarity(query_vec, doc_vec)
        chunk_len = len(chunk_text)
        preview = chunk_text[:160].replace("\n", " ")

        rows.append({
            "rank": rank,
            "store_score": round(float(store_score), 4) if store_score is not None else None,
            "cosine_sim": round(cos_sim, 4),
            "chunk_len": chunk_len,
            "preview": preview,
            "source_file": node_with_score.node.metadata.get("source_file", "unknown"),
        })

    doc_matrix = np.stack(doc_vecs) if doc_vecs else np.array([])
    print(f"Query vector shape: {query_vec.shape}")
    print(f"Stacked doc vectors shape: {doc_matrix.shape}")

    print(f"\n{'rank':<5}{'store_score':<13}{'cosine_sim':<12}{'chunk_len':<11}preview")
    for row in rows:
        print(f"{row['rank']:<5}{row['store_score']:<13}{row['cosine_sim']:<12}"
              f"{row['chunk_len']:<11}{row['preview'][:80]}")

    return {
        "technique": technique_name,
        "query": query,
        "latency_ms": round(latency_ms, 2),
        "query_embedding_dim": int(query_vec.shape[0]),
        "results": rows,
    }


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    print("Loading corpus documents...")
    documents = load_documents()
    print(f"  Loaded {len(documents)} documents.")

    print("Loading questions...")
    questions = load_questions()
    print(f"  Loaded {len(questions)} questions.")

    print(f"\nLoading embedding model ({EMBED_MODEL_NAME})...")
    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
    print("  Model loaded.")

    print("\nBuilding indexes for all three techniques...")
    print("  Building Token index...")
    token_index, token_nodes = build_token_index(documents, embed_model)
    print(f"    {len(token_nodes)} chunks produced.")

    print("  Building Semantic index (this can take a while - embeds during chunking)...")
    semantic_index, semantic_nodes = build_semantic_index(documents, embed_model)
    print(f"    {len(semantic_nodes)} chunks produced.")

    print("  Building Sentence-window index...")
    sw_index, sw_nodes = build_sentence_window_index(documents, embed_model)
    print(f"    {len(sw_nodes)} chunks produced.")

    indexes = {
        "Token": (token_index, token_nodes),
        "Semantic": (semantic_index, semantic_nodes),
        "SentenceWindow": (sw_index, sw_nodes),
    }

    # Run retrieval for every (technique, question) pair
    all_results = []
    for technique_name, (index, nodes) in indexes.items():
        for q in questions:
            result = retrieve_and_analyze(
                technique_name, index, embed_model, q["question"], k=TOP_K
            )
            result["question_id"] = q["id"]
            result["expected_source_file"] = q["expected_source_file"]
            all_results.append(result)

    # Save raw results (JSON, and a flattened CSV for the per-row data)
    raw_json_path = RAW_DIR / "chunking_comparison_raw.json"
    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    raw_csv_path = RAW_DIR / "chunking_comparison_raw.csv"
    with open(raw_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "technique", "question_id", "query", "latency_ms", "rank",
            "store_score", "cosine_sim", "chunk_len", "preview", "source_file",
            "expected_source_file",
        ])
        writer.writeheader()
        for result in all_results:
            for row in result["results"]:
                writer.writerow({
                    "technique": result["technique"],
                    "question_id": result["question_id"],
                    "query": result["query"],
                    "latency_ms": result["latency_ms"],
                    "expected_source_file": result["expected_source_file"],
                    **row,
                })

    # Chunk-count / avg-length summary per technique
    chunk_summary = {}
    for technique_name, (index, nodes) in indexes.items():
        lengths = [len(n.get_content()) for n in nodes]
        chunk_summary[technique_name] = {
            "num_chunks": len(nodes),
            "avg_chunk_length_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        }

    summary_path = RAW_DIR / "chunk_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(chunk_summary, f, indent=2)

    print(f"\n\n{'='*70}")
    print("Chunk summary per technique:")
    print(json.dumps(chunk_summary, indent=2))
    print(f"\nRaw results saved to: {raw_json_path}")
    print(f"Raw results (CSV) saved to: {raw_csv_path}")
    print(f"Chunk summary saved to: {summary_path}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()