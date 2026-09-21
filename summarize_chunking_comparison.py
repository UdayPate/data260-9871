import json
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RAW_DIR = REPO_ROOT / "reports" / "hw03" / "raw"

RAW_RESULTS_FILE = RAW_DIR / "chunking_comparison_raw.json"
CHUNK_SUMMARY_FILE = RAW_DIR / "chunk_summary.json"
OUTPUT_FILE = RAW_DIR / "final_summary_table.json"


def main():
    with open(RAW_RESULTS_FILE, "r", encoding="utf-8") as f:
        raw_results = json.load(f)

    with open(CHUNK_SUMMARY_FILE, "r", encoding="utf-8") as f:
        chunk_summary = json.load(f)

    techniques = sorted(set(r["technique"] for r in raw_results))

    final_table = {}

    for technique in techniques:
        technique_results = [r for r in raw_results if r["technique"] == technique]

        top1_cosines = []
        mean_at_k_cosines = []
        latencies = []
        recall_hits = []

        for result in technique_results:
            rows = result["results"]
            if not rows:
                continue

            # Top-1 cosine: the cosine_sim of the rank=1 result
            rank1 = next((row for row in rows if row["rank"] == 1), rows[0])
            top1_cosines.append(rank1["cosine_sim"])

            # Mean@k cosine: average cosine_sim across all k retrieved results
            mean_at_k_cosines.append(
                statistics.mean(row["cosine_sim"] for row in rows)
            )

            # Recall@k: did the expected source file appear anywhere in top-k?
            expected = result["expected_source_file"]
            hit = any(row["source_file"] == expected for row in rows)
            recall_hits.append(1 if hit else 0)

            latencies.append(result["latency_ms"])

        final_table[technique] = {
            "num_chunks": chunk_summary[technique]["num_chunks"],
            "avg_chunk_length_chars": chunk_summary[technique]["avg_chunk_length_chars"],
            "top1_cosine_mean": round(statistics.mean(top1_cosines), 4),
            "mean_at_k_cosine": round(statistics.mean(mean_at_k_cosines), 4),
            "recall_at_k": round(statistics.mean(recall_hits), 4),
            "recall_at_k_hits": f"{sum(recall_hits)}/{len(recall_hits)}",
            "mean_retrieval_latency_ms": round(statistics.mean(latencies), 2),
        }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_table, f, indent=2)

    # Print as a readable table
    print(f"{'Technique':<16}{'Chunks':<9}{'AvgLen':<10}{'Top1Cos':<10}"
          f"{'Mean@kCos':<11}{'Recall@k':<11}{'LatencyMS':<11}")
    print("-" * 78)
    for technique, stats in final_table.items():
        print(f"{technique:<16}{stats['num_chunks']:<9}"
              f"{stats['avg_chunk_length_chars']:<10}"
              f"{stats['top1_cosine_mean']:<10}"
              f"{stats['mean_at_k_cosine']:<11}"
              f"{stats['recall_at_k_hits']:<11}"
              f"{stats['mean_retrieval_latency_ms']:<11}")

    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()