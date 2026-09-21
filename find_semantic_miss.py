import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
raw_path = REPO_ROOT / "reports" / "hw03" / "raw" / "chunking_comparison_raw.json"

with open(raw_path) as f:
    raw = json.load(f)

for r in raw:
    if r["technique"] == "Semantic":
        expected = r["expected_source_file"]
        sources = [row["source_file"] for row in r["results"]]
        hit = expected in sources
        if not hit:
            print(f"MISS: question_id={r['question_id']}")
            print(f"  Query: {r['query']}")
            print(f"  Expected source: {expected}")
            print(f"  Actually retrieved sources: {sources}")
            print(f"  Top result cosine_sim: {r['results'][0]['cosine_sim']}")
            print(f"  Top result preview: {r['results'][0]['preview'][:150]}")