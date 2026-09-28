"""
DATA-260 Homework 4 - Part 4: Grounded RAG question-answering system.

Builds a small RAG app over the six league rulebooks reused from HW3, then
compares three configurations on six typed questions:

  (A) No RAG               - question straight to the LLM (baseline)
  (B) Basic RAG            - top-3 raw chunks pasted into the prompt
  (C) Context-engineered   - low-relevance and near-duplicate chunks dropped,
                             survivors ordered + labelled with their sources,
                             plus grounding rules (cite [n], refuse when the
                             evidence is insufficient)

It also sweeps top_k (1, 3, 5) and writes an evaluation table. Everything goes
through src/model_client.py at temperature 0 to minimise run-to-run variation. Note this
does not make runs identical: qwen3's hidden reasoning length still varies between calls.

Usage (from the repo root):
  python rag.py --retrieval-only   # build index, print retrieval + what context
                                   # engineering would keep/drop. No LLM calls.
  python rag.py                    # full run
  python rag.py --chunk-size 1000 --out reports/hw04/raw_chunk1000

Chunk size / overlap are counted in CHARACTERS (see chunk_text). all-MiniLM-L6-v2
only embeds ~256 word-pieces, so 500 characters fits entirely inside its window.
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import yaml
from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode

REPO_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
CORPUS_DIR = REPO_ROOT / "reports" / "hw03" / "corpus"
QUESTIONS_PATH = REPO_ROOT / "reports" / "hw04" / "questions.yaml"
OUT_DIR = REPO_ROOT / "reports" / "hw04" / "raw"

CHUNK_SIZE = 500          # characters
CHUNK_OVERLAP = 50        # characters
TOP_K = 3
MIN_SCORE = 0.30          # context engineering: drop chunks scoring below this.
                          # A starting guess - calibrate it from the scores that
                          # `--retrieval-only` prints, then pass --min-score.
DEDUP_JACCARD = 0.80      # context engineering: near-duplicate threshold
SWEEP_KS = [1, 3, 5]
SWEEP_QUESTIONS = ["q2", "q3", "q5"]

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "qwen3:8b"
REFUSAL = "I cannot answer this question from the provided documents"

# Automatic-scoring aids. These regexes come straight from the expected answers
# committed in questions.yaml; they are a transparent heuristic, not a judge.
FACT_PATTERNS = {
    "q1": [r"\b85\b", r"4\.25"],
    "q2": [r"\b12\b", r"\bhour\b|\b60\s*min"],
    # Q3: match a team-size STATEMENT ("4-a-side", "4 players", "4 per side", "4v4"), not any
    # stray digit - a bare \b5\b matched the "6 5" table columns in a real answer.
    "q3": [r"\b(4|four)\W*(a\W*side|players?|per\s+side)|\b4\s*v\s*4\b",
           r"\b(5|five)\W*(a\W*side|players?|per\s+side)|\b5\s*v\s*5\b"],
}
# For "correct retrieval": per expected source file, text that must appear in the
# chunks retrieved from THAT file. Requiring the answer-bearing text (not merely
# any chunk from the right file) keeps a retrieval failure visible. \W tolerates
# the odd hyphen/dash characters the PDFs were extracted with.
EVIDENCE_PATTERNS = {
    "q1": {"cricket_uspl_t20_rules.txt": [r"\b85\b", r"4\.25"]},
    "q2": {"general_douglas_county_all_sports_rules.txt": [r"maximum\W*12\b"],
           "volleyball_fort_collins_manual.txt": [r"\(1\)\s*hour|\bone hour|\b1[- ]hour|hour time limit"]},
    "q3": {"soccer_ayso_national_rules.txt": [r"8u\W+4\W*a\W*side"],
           "soccer_ayso_basic_rules.txt": [r"5\W*a\W*side\W+for\W+u\W*8"]},
}
SPORT_WORDS = ["soccer", "basketball", "cricket", "volleyball"]
CLARIFY_CUES = (r"which sport|specify|clarif|depends on (the )?sport|different sports|"
                r"varies (by|between|across)|not specif|ambigu|could you|please tell")
STRESS_QUESTIONS = ["q3", "q4", "q5", "q6"]


# ---------------------------------------------------------------------------
# Corpus -> chunks
# ---------------------------------------------------------------------------
def normalize_text(text):
    """Tidy whitespace (the PDFs contain non-breaking spaces, CRLFs, page-break
    runs) so character counts mean something."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0\u2002\u2003\u2009]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Sliding window of at most `size` characters, consecutive windows sharing
    about `overlap` characters. Boundaries snap to whitespace so no word is cut
    in half."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks, n, start = [], len(text), 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind(" "), window.rfind("\n"))
            if cut > size // 2:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        nxt = max(end - overlap, start + 1)
        while nxt < end and not text[nxt - 1].isspace():
            nxt += 1                      # start the next chunk on a word boundary
        start = nxt if nxt > start else end
    return chunks


def build_nodes(corpus_dir, size, overlap):
    """One TextNode per chunk, carrying text, source file name and chunk_id.
    Metadata is excluded from BOTH the embedding text and the LLM text, so the
    file name cannot leak into retrieval scores."""
    nodes, per_doc = [], {}
    for path in sorted(Path(corpus_dir).glob("*.txt")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(normalize_text(raw), size, overlap)
        per_doc[path.name] = {"characters": len(raw), "chunks": len(chunks)}
        for i, piece in enumerate(chunks):
            cid = f"{path.stem}::{i:04d}"
            node = TextNode(text=piece, id_=cid,
                            metadata={"source": path.name, "chunk_id": cid})
            node.excluded_embed_metadata_keys = ["source", "chunk_id"]
            node.excluded_llm_metadata_keys = ["source", "chunk_id"]
            nodes.append(node)
    if len(per_doc) < 5:
        raise SystemExit(f"Need at least 5 documents in {corpus_dir}, found {len(per_doc)}")
    return nodes, per_doc


def get_embed_model():
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    return HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)


def retrieve(index, question, k):
    """Top-k chunks as plain dicts (rank, source, chunk_id, cosine score, text)."""
    results = index.as_retriever(similarity_top_k=k).retrieve(question)
    return [{
        "rank": rank,
        "source": r.node.metadata["source"],
        "chunk_id": r.node.metadata["chunk_id"],
        "score": float(r.score),
        "text": r.node.get_content(),
    } for rank, r in enumerate(results, 1)]


# ---------------------------------------------------------------------------
# Context engineering (configuration C)
# ---------------------------------------------------------------------------
def _words(text):
    return set(re.findall(r"\w+", text.lower()))


def _find_duplicate(chunk, kept, threshold):
    a = _words(chunk["text"])
    for other in kept:
        b = _words(other["text"])
        if a == b:
            return other["chunk_id"]
        if a and b and len(a & b) / len(a | b) >= threshold:
            return other["chunk_id"]
    return None


def context_engineer(chunks, min_score=MIN_SCORE, jaccard=DEDUP_JACCARD):
    """Drop chunks below `min_score`, drop near-duplicates of a higher-scoring
    chunk, and return the survivors best-first with the reason for every drop."""
    kept, dropped = [], []
    for c in sorted(chunks, key=lambda x: -x["score"]):
        if c["score"] < min_score:
            dropped.append({**c, "reason": f"score {c['score']:.3f} < min_score {min_score}"})
            continue
        dup = _find_duplicate(c, kept, jaccard)
        if dup:
            dropped.append({**c, "reason": f"near-duplicate of {dup}"})
            continue
        kept.append(c)
    return kept, dropped


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
GROUNDING_RULES = f"""You answer questions about community sports league rules using ONLY the numbered sources in the context.
Rules:
1. Use only facts stated in the sources. Do not use outside knowledge.
2. Cite the source number in square brackets, like [1], after each fact you use.
3. If the sources do not contain enough information to answer, reply with exactly: {REFUSAL}.
4. If sources disagree, state each value and cite each source; say which file each comes from.
5. If the question is ambiguous (for example it does not say which sport), say what is ambiguous and answer only for the interpretations the sources support, citing them. Do not guess."""


def prompt_a(question):
    return [{"role": "user", "content": question}]


def prompt_b(question, chunks):
    context = "\n\n".join(c["text"] for c in chunks)
    return [
        {"role": "system", "content": "You are a helpful assistant. Answer the question using the context provided."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"},
    ]


def prompt_c(question, kept):
    if kept:
        context = "\n\n".join(
            f"[{i}] (source file: {c['source']}, chunk: {c['chunk_id']})\n{c['text']}"
            for i, c in enumerate(kept, 1))
    else:
        context = "(No relevant sources were found.)"
    return [
        {"role": "system", "content": GROUNDING_RULES},
        {"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {question}\nAnswer:"},
    ]


# ---------------------------------------------------------------------------
# Scoring (automatic heuristics - review the raw answers too)
# ---------------------------------------------------------------------------
def _strip_cites(text):
    return re.sub(r"\[\d+\]", " ", text)


def is_refusal(answer):
    return REFUSAL.lower() in re.sub(r"\s+", " ", answer).lower()


def _sports_in(text):
    t = text.lower()
    return {s for s in SPORT_WORDS if s in t}


def irrelevant_count(q, chunks):
    """Chunks that cannot help: wrong source file, or ANY chunk when the
    question should be refused. None when there is no notion of 'irrelevant'."""
    if q["expected_behavior"] == "refuse":
        return len(chunks)
    if q["expected_sources"]:
        return sum(1 for c in chunks if c["source"] not in q["expected_sources"])
    return None


def evidence_retrieved(qid, chunks):
    """True only if every expected source file contributed a chunk containing
    its answer-bearing text. None if we have no evidence patterns for qid."""
    required = EVIDENCE_PATTERNS.get(qid)
    if required is None:
        return None
    for source, patterns in required.items():
        text = " ".join(c["text"] for c in chunks if c["source"] == source).lower()
        if not all(re.search(p, text) for p in patterns):
            return False
    return True


def score_row(q, config, answer, ctx_chunks):
    qid, behavior = q["id"], q["expected_behavior"]
    refused = is_refusal(answer)
    a = _strip_cites(answer).lower()
    ctx_text = _strip_cites("\n".join(c["text"] for c in ctx_chunks)).lower()
    ctx_sources = sorted({c["source"] for c in ctx_chunks})
    facts = FACT_PATTERNS.get(qid, [])

    # -- correct answer -----------------------------------------------------
    if behavior == "refuse":
        correct = refused
    elif behavior == "answer":
        correct = (not refused) and all(re.search(p, a) for p in facts)
    elif behavior == "answer_and_flag_conflict":
        correct = (not refused) and all(re.search(p, a) for p in facts)
    else:  # clarify_or_answer_per_sport_without_inventing
        correct = (not refused) and (bool(re.search(CLARIFY_CUES, a)) or len(_sports_in(a)) >= 2)

    # -- correct retrieval (only meaningful for RAG configs with expected sources)
    if config == "A" or not q["expected_sources"]:
        correct_retrieval = None
    else:
        correct_retrieval = evidence_retrieved(qid, ctx_chunks)

    # -- grounded: is what the answer states supported by the context it was given
    if config == "A":
        grounded = None
    elif refused:
        grounded = True
    elif behavior == "refuse":
        grounded = False          # it answered something the documents cannot support
    elif facts:
        in_answer = [p for p in facts if re.search(p, a)]
        grounded = bool(in_answer) and all(re.search(p, ctx_text) for p in in_answer)
    else:
        grounded = _sports_in(a) <= _sports_in(ctx_text)

    cites = bool(re.search(r"\[\d+\]", answer))
    refusal_needed = behavior == "refuse"
    return {
        "correct_retrieval": correct_retrieval,
        "correct_answer": bool(correct),
        "grounded": grounded,
        "refused": refused,
        "refused_when_needed": refused if refusal_needed else None,
        "false_refusal": refused and not refusal_needed,
        "cites_source": cites,
        "format_ok": (refused or cites) if config == "C" else None,
        "context_sources": ctx_sources,
    }


def _rate(values):
    vals = [v for v in values if v is not None]
    return None if not vals else round(sum(1 for v in vals if v) / len(vals), 3)


def summarize(rows):
    out = {}
    for cfg in ("A", "B", "C"):
        r = [x for x in rows if x["config"] == cfg]
        out[cfg] = {
            "accuracy": _rate([x["correct_answer"] for x in r]),
            "faithfulness": _rate([x["grounded"] for x in r]),
            "format_compliance": _rate([x["format_ok"] for x in r]),
            "robustness": _rate([x["correct_answer"] for x in r if x["qid"] in STRESS_QUESTIONS]),
        }
    return out


# ---------------------------------------------------------------------------
# Running the model
# ---------------------------------------------------------------------------
def ask(client, messages):
    tin0 = getattr(client, "cumulative_input_tokens", 0)
    tout0 = getattr(client, "cumulative_output_tokens", 0)
    t0 = time.perf_counter()
    answer = client.complete(messages)
    return answer, {
        "input_tokens": getattr(client, "cumulative_input_tokens", 0) - tin0,
        "output_tokens": getattr(client, "cumulative_output_tokens", 0) - tout0,
        "latency_s": round(time.perf_counter() - t0, 2),
    }


def run_config(client, q, config, chunks, min_score):
    """Build the right prompt for A/B/C, ask the model, score the answer."""
    dropped = []
    if config == "A":
        ctx = []
        messages = prompt_a(q["question"])
    elif config == "B":
        ctx = chunks
        messages = prompt_b(q["question"], ctx)
    else:
        ctx, dropped = context_engineer(chunks, min_score)
        messages = prompt_c(q["question"], ctx)
    answer, usage = ask(client, messages)
    row = {
        "qid": q["id"], "config": config, "question": q["question"],
        "answer": answer,
        "context_chunk_ids": [c["chunk_id"] for c in ctx],
        "dropped": [{"chunk_id": d["chunk_id"], "reason": d["reason"]} for d in dropped],
        "context_chars": sum(len(c["text"]) for c in ctx),
        **usage,
        **score_row(q, config, answer, ctx),
        "messages": messages,
    }
    return row


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def yn(v):
    return "n/a" if v is None else ("yes" if v else "NO")


def markdown_table(rows, summary):
    lines = ["## Per-question results", "",
             "| Q | Config | Correct retrieval | Correct answer | Grounded | Refused when needed | Cites source |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['qid']} | {r['config']} | {yn(r['correct_retrieval'])} | {yn(r['correct_answer'])} | "
                     f"{yn(r['grounded'])} | {yn(r['refused_when_needed'])} | {yn(r['cites_source'])} |")
    lines += ["", "## Summary", "",
              "| Config | Accuracy | Faithfulness | Format compliance | Robustness (Q3-Q6) |",
              "|---|---|---|---|---|"]
    names = {"A": "A: No RAG", "B": "B: Basic RAG", "C": "C: Context-engineered"}
    for cfg, s in summary.items():
        f = lambda v: "n/a" if v is None else f"{v:.0%}"
        lines.append(f"| {names[cfg]} | {f(s['accuracy'])} | {f(s['faithfulness'])} | "
                     f"{f(s['format_compliance'])} | {f(s['robustness'])} |")
    lines += ["", "Definitions: accuracy = share of the 6 questions handled as expected (right answer, or a "
              "refusal where one was needed); faithfulness = share of RAG answers supported by the context they "
              "were given; format compliance = share of config C answers that cite a [n] source or use the exact "
              "refusal sentence (A and B were never told to, so n/a); robustness = accuracy on the four stress "
              "questions Q3-Q6. All values are automatic heuristics - check them against the saved raw answers."]
    return "\n".join(lines)


COMPARISON_FIELDS = ["qid", "config", "answer", "context_chunk_ids", "context_chars", "input_tokens",
                     "output_tokens", "latency_s", "correct_retrieval", "correct_answer", "grounded",
                     "refused", "refused_when_needed", "false_refusal", "cites_source", "format_ok"]
SWEEP_FIELDS = ["qid", "config", "k", "irrelevant_chunks_retrieved", "context_chars", "input_tokens",
                "correct_retrieval", "correct_answer", "grounded", "refused", "answer"]


def save_comparison(out_dir, rows):
    write_json(out_dir / "three_config_comparison.json", rows)
    write_csv(out_dir / "three_config_comparison.csv", rows, COMPARISON_FIELDS)


def save_sweep(out_dir, sweep):
    write_json(out_dir / "k_sweep.json", sweep)
    write_csv(out_dir / "k_sweep.csv", sweep, SWEEP_FIELDS)


def save_evaluation(out_dir, rows):
    """Write evaluation_table.{json,csv,md}; returns (markdown, summary)."""
    summary = summarize(rows)
    table_rows = [{k: r[k] for k in ("qid", "config", "correct_retrieval", "correct_answer", "grounded",
                                     "refused_when_needed", "false_refusal", "cites_source", "format_ok")}
                  for r in rows]
    write_json(out_dir / "evaluation_table.json", {"per_question": table_rows, "summary": summary})
    write_csv(out_dir / "evaluation_table.csv", table_rows, list(table_rows[0].keys()))
    md = markdown_table(rows, summary)
    (out_dir / "evaluation_table.md").write_text(md, encoding="utf-8")
    return md, summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def resolve(p):
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def run(args, embed_model=None, client=None):
    out_dir = resolve(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript = []

    def emit(line=""):
        print(line)
        transcript.append(line)

    def finish():
        (out_dir / "run_transcript.txt").write_text("\n".join(transcript), encoding="utf-8")

    questions = yaml.safe_load(resolve(args.questions).read_text(encoding="utf-8"))["questions"]
    nodes, per_doc = build_nodes(resolve(args.corpus), args.chunk_size, args.chunk_overlap)

    emit("=== Corpus and index ===")
    for name, info in per_doc.items():
        emit(f"  {name:<50} {info['characters']:>8} chars  {info['chunks']:>4} chunks")
    emit(f"  total: {len(per_doc)} documents, {len(nodes)} chunks "
         f"(chunk_size={args.chunk_size}, overlap={args.chunk_overlap} characters)")

    index = VectorStoreIndex(nodes, embed_model=embed_model or get_embed_model())
    write_json(out_dir / "run_config.json", {
        "chunk_size_chars": args.chunk_size, "chunk_overlap_chars": args.chunk_overlap,
        "top_k": TOP_K, "min_score": args.min_score, "dedup_jaccard": DEDUP_JACCARD,
        "embedding_model": EMBED_MODEL_NAME, "llm": args.model, "temperature": 0.0,
        "documents": per_doc, "total_chunks": len(nodes), "sweep_ks": SWEEP_KS,
        "sweep_questions": args.sweep_questions,
    })

    # ---- Step 2: retrieval, printed before any LLM call ---------------------
    emit("\n=== Retrieval (top_k=3), printed before calling the LLM ===")
    retrieval = {}
    for q in questions:
        chunks = retrieve(index, q["question"], TOP_K)
        retrieval[q["id"]] = chunks
        emit(f"\n{q['id']} [{q['type']}]: {q['question']}")
        for c in chunks:
            snippet = c["text"].replace("\n", " ")
            emit(f"  [{c['rank']}] score={c['score']:.4f}  {c['source']}  {c['chunk_id']}")
            emit(f"      {snippet[:300]}{'...' if len(snippet) > 300 else ''}")
    write_json(out_dir / "retrieved_top3.json", retrieval)

    if args.retrieval_only:
        emit(f"\n=== Context engineering preview (min_score={args.min_score}) ===")
        for q in questions:
            kept, dropped = context_engineer(retrieval[q["id"]], args.min_score)
            emit(f"{q['id']}: keep {len(kept)}, drop {len(dropped)}")
            for d in dropped:
                emit(f"    dropped {d['chunk_id']}: {d['reason']}")
        emit("\nRetrieval-only run: no LLM calls made. Compare the scores above for the questions that "
             "have answers (Q1-Q3) against Q5/Q6 to choose --min-score.")
        finish()
        return

    client = client or _make_client(args.model)

    # ---- Step 3: three configurations x six questions -----------------------
    emit("\n=== Three-configuration comparison ===")
    rows = []
    for q in questions:
        for cfg in ("A", "B", "C"):
            row = run_config(client, q, cfg, retrieval[q["id"]], args.min_score)
            rows.append(row)
            emit(f"\n--- {q['id']} / config {cfg} "
                 f"(context chunks: {len(row['context_chunk_ids'])}, input tokens: {row['input_tokens']}) ---")
            for d in row["dropped"]:
                emit(f"  [dropped {d['chunk_id']}: {d['reason']}]")
            emit(row["answer"])
    save_comparison(out_dir, rows)

    # ---- Step 5: top_k sweep ------------------------------------------------
    emit("\n=== top_k sweep ===")
    by_id = {q["id"]: q for q in questions}
    sweep = []
    for qid in args.sweep_questions:
        q = by_id[qid]
        for k in SWEEP_KS:
            chunks = retrieve(index, q["question"], k)
            for cfg in ("B", "C"):
                row = run_config(client, q, cfg, chunks, args.min_score)
                row.update({
                    "k": k,
                    "retrieved": [{"source": c["source"], "chunk_id": c["chunk_id"],
                                   "score": round(c["score"], 4)} for c in chunks],
                    "irrelevant_chunks_retrieved": irrelevant_count(q, chunks),
                })
                sweep.append(row)
                emit(f"{qid} k={k} cfg={cfg}: chunks_in_prompt={len(row['context_chunk_ids'])} "
                     f"irrelevant_retrieved={row['irrelevant_chunks_retrieved']} "
                     f"correct={yn(row['correct_answer'])} grounded={yn(row['grounded'])} "
                     f"input_tokens={row['input_tokens']}")
    save_sweep(out_dir, sweep)

    # ---- Step 6: evaluation table -------------------------------------------
    md, _ = save_evaluation(out_dir, rows)
    emit("\n=== Evaluation table (automatic heuristics) ===\n" + md)
    emit(f"\nSaved everything to {out_dir}")
    finish()


def _make_client(model):
    try:
        from src.model_client import ModelClient
    except ImportError:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from model_client import ModelClient
    return ModelClient(model=model, temperature=0.0)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="HW4 Part 4 grounded RAG")
    p.add_argument("--retrieval-only", action="store_true")
    p.add_argument("--min-score", type=float, default=MIN_SCORE)
    p.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    p.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP)
    p.add_argument("--corpus", default=str(CORPUS_DIR))
    p.add_argument("--questions", default=str(QUESTIONS_PATH))
    p.add_argument("--out", default=str(OUT_DIR))
    p.add_argument("--model", default=LLM_MODEL)
    p.add_argument("--sweep-questions", type=lambda s: s.split(","), default=SWEEP_QUESTIONS)
    return p.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())