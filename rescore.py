"""
DATA-260 Homework 4 - Part 4: re-score saved answers with the current scoring rules.

Use this after changing the scoring heuristics in rag.py. It makes NO model calls
and computes NO embeddings: it reloads the saved answers from the raw/ folder,
rebuilds each chunk's text from the corpus (chunking is deterministic), re-scores
every row, and regenerates the results files.

The original scoring is copied to raw/first_pass_scoring/ the first time this runs,
so both versions stay on record. Every verdict that changes is printed.

  python rescore.py
"""

import argparse
import json
import shutil

import yaml

import rag

WATCHED = ["correct_retrieval", "correct_answer", "grounded", "refused_when_needed",
           "false_refusal", "format_ok"]
BACKUP_FILES = ["three_config_comparison.json", "three_config_comparison.csv", "k_sweep.json",
                "k_sweep.csv", "evaluation_table.json", "evaluation_table.csv", "evaluation_table.md"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(rag.OUT_DIR))
    ap.add_argument("--corpus", default=str(rag.CORPUS_DIR))
    ap.add_argument("--questions", default=str(rag.QUESTIONS_PATH))
    ap.add_argument("--chunk-size", type=int, default=rag.CHUNK_SIZE)
    ap.add_argument("--chunk-overlap", type=int, default=rag.CHUNK_OVERLAP)
    args = ap.parse_args(argv)

    out = rag.resolve(args.out)
    questions = {q["id"]: q for q in
                 yaml.safe_load(rag.resolve(args.questions).read_text(encoding="utf-8"))["questions"]}
    rows = json.loads((out / "three_config_comparison.json").read_text(encoding="utf-8"))
    sweep_path = out / "k_sweep.json"
    sweep = json.loads(sweep_path.read_text(encoding="utf-8")) if sweep_path.exists() else []

    # keep the original scoring, once
    backup = out / "first_pass_scoring"
    if not backup.exists():
        backup.mkdir()
        for name in BACKUP_FILES:
            if (out / name).exists():
                shutil.copy(out / name, backup / name)
        print(f"Original scoring saved to {backup}")

    nodes, _ = rag.build_nodes(rag.resolve(args.corpus), args.chunk_size, args.chunk_overlap)
    by_id = {n.node_id: {"chunk_id": n.node_id, "source": n.metadata["source"], "text": n.get_content()}
             for n in nodes}

    changes = []

    def rescore(rs, label):
        for r in rs:
            ctx = [by_id[c] for c in r["context_chunk_ids"]]
            if sum(len(c["text"]) for c in ctx) != r["context_chars"]:
                raise SystemExit(f"Corpus or chunk settings differ from the saved run ({r['qid']}/{r['config']}). "
                                 "Rescoring would be unreliable; aborting.")
            old = {k: r.get(k) for k in WATCHED}
            r.update(rag.score_row(questions[r["qid"]], r["config"], r["answer"], ctx))
            for k in WATCHED:
                if old[k] != r.get(k):
                    tag = f"{label} {r['qid']}/{r['config']}" + (f" k={r['k']}" if "k" in r else "")
                    changes.append(f"  {tag}: {k} {rag.yn(old[k])} -> {rag.yn(r.get(k))}")

    rescore(rows, "main ")
    rescore(sweep, "sweep")

    rag.save_comparison(out, rows)
    if sweep:
        rag.save_sweep(out, sweep)
    md, _ = rag.save_evaluation(out, rows)

    print(f"\nVerdicts changed by the corrected scoring rules ({len(changes)}):")
    print("\n".join(changes) if changes else "  (none)")
    print("\n=== Evaluation table after re-scoring ===\n" + md)
    if sweep:
        print("\n=== top_k sweep after re-scoring ===")
        for r in sweep:
            print(f"{r['qid']} k={r['k']} cfg={r['config']}: retrieval={rag.yn(r['correct_retrieval'])} "
                  f"correct={rag.yn(r['correct_answer'])} grounded={rag.yn(r['grounded'])} "
                  f"irrelevant_retrieved={r['irrelevant_chunks_retrieved']} input_tokens={r['input_tokens']}")


if __name__ == "__main__":
    main()