"""
DATA-260 Homework 9 - Part 3.3: one false hit in full. Selection rule (fixed here, before the real run): of the `different_answer`
cases served from the cache at the default threshold 0.85, take the one with the HIGHEST similarity. Writes raw/part3_false_hit.json.
Everything shown is read live: the cached answer from Redis, the correct answer from s9871_rel, the tokens from the MiniLM tokenizer.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import semantic_cache as sc  # noqa: E402
from facts import fixture_facts  # noqa: E402
from validate_cases import answer_from_facts, load_cases  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    sweep = json.load(open(ROOT / "reports/hw09/raw/part3_sweep.json", encoding="utf-8"))
    rows85 = next(t for t in sweep["thresholds"] if t["threshold"] == 0.85)["rows"]
    pick = max((r for r in rows85 if r["category"] == "different_answer" and r["false_hit"]), key=lambda r: r["similarity"])
    data = load_cases()
    case = next(c for c in data["cases"] if c["id"] == pick["id"])
    cache = sc.SemanticCache()
    best = cache.nearest(sc.embed(case["query"]))  # live lookup; the cache was seeded by the sweep
    correct = answer_from_facts(fixture_facts([case["fixture"]])[case["fixture"]], case["attribute"])
    tok = sc._model.tokenizer.tokenize
    a, b = tok(best["query"]), tok(case["query"])
    diff = [(x, y) for x, y in zip(a, b, strict=False) if x != y]
    # for scale: how similar are a TRUE paraphrase pair and an unrelated pair, under the same model
    para = next(c for c in data["cases"] if c["id"] == "C14")
    seed4 = next(s for s in data["seeds"] if s["id"] == "S04")
    para_sim = float(sc.embed(para["query"]) @ sc.embed(seed4["query"]))
    out = {"case_id": case["id"], "incoming_query": case["query"], "cached_query": best["query"], "similarity": best["similarity"],
           "threshold": 0.85, "cached_answer_returned": best["answer"], "correct_answer": correct, "answers_differ": best["answer"] != correct,
           "tokens_cached": a, "tokens_incoming": b, "differing_token_pairs": diff, "n_tokens": len(a),
           "true_paraphrase_for_scale": {"case": para["id"], "query": para["query"], "vs": seed4["query"], "similarity": round(para_sim, 4)}}
    (ROOT / "reports/hw09/raw/part3_false_hit.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
