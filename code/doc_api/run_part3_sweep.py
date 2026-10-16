"""
DATA-260 Homework 6 - Part 3 experiment driver.

For each setting (SHORT_TERM_N = 4 / 12 / 30, plus the "compress" policy) it runs the
SAME fixed conversation (part3_conversation.json) in a fresh user/session against the
running API (real Ollama model, real MongoDB), then asks the five memory probes from
reports/hw06/memory_probes.yaml with read_only=true, scores them, and writes:
  <out>/part3_turns.csv      one row per /api/chat turn (tokens, components, latency)
  <out>/part3_probes.json    every probe answer, matched elements, score
  <out>/part3_summary.json   per-setting means (+ settings snapshot)

Usage (server on 8871):
  python run_part3_sweep.py [--turns 30] [--configs N4,N12,N30,COMPRESS]
                            [--tag p3] [--out ../../reports/hw06/raw] [--repeat 1]
"""

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from pymongo import MongoClient

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8871"
PROBES_YAML = HERE.parents[1] / "reports" / "hw06" / "memory_probes.yaml"

CONFIGS = {
    "N4":       {"POLICY": "none", "SHORT_TERM_N": 4},
    "N12":      {"POLICY": "none", "SHORT_TERM_N": 12},
    "N30":      {"POLICY": "none", "SHORT_TERM_N": 30},
    "COMPRESS": {"POLICY": "compress", "SHORT_TERM_N": 30,
                 "COMPRESS_KEEP_LAST": 6, "COMPRESS_SUMMARY_EVERY": 3},
}
COMPONENTS = ["system_primer", "long_term_summary", "short_term_window",
              "episodic_facts", "current_message", "template_overhead"]


def score_answer(answer: str, probe: dict, rubric: dict) -> dict:
    low = answer.lower()
    matched = [e["name"] for e in probe["elements"] if any(k in low for k in e["any_of"])]
    contradicted = [c for c in probe.get("contradictions", []) if c in low]
    hedged = any(h in low for h in rubric["hedge_phrases"])
    frac = len(matched) / len(probe["elements"])
    if frac == 1 and not contradicted:
        score = 4 if hedged else 5
    elif frac == 1:
        score = 3
    elif frac >= 0.5:
        score = 3
    elif frac > 0:
        score = 2
    else:
        score = 1
    return {"matched": matched, "contradicted": contradicted, "hedged": hedged, "score": score}


def post_chat(payload, retries=2):
    for attempt in range(retries + 1):
        r = requests.post(f"{BASE}/api/chat", json=payload, timeout=300)
        if r.status_code == 200:
            return r.json()
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        time.sleep(2)
    raise RuntimeError("chat request kept failing")


def warm_up():
    """One throwaway read-only call so model load / tokenizer / embedder start-up
    time is never counted in a measured turn."""
    t0 = time.perf_counter()
    post_chat({"user_id": "p3_warmup", "message": "Hello, are you ready?", "read_only": True})
    print(f"  warm-up call: {time.perf_counter() - t0:.1f}s (not measured)")


def mean(xs):
    return round(statistics.fmean(xs), 2) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=30)
    ap.add_argument("--configs", default="N4,N12,N30,COMPRESS")
    ap.add_argument("--tag", default="p3")
    ap.add_argument("--out", default=str(HERE.parents[1] / "reports" / "hw06" / "raw"))
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    convo = json.loads((HERE / "part3_conversation.json").read_text(encoding="utf-8"))["messages"][:args.turns]
    spec = yaml.safe_load(PROBES_YAML.read_text(encoding="utf-8"))
    probes, rubric = spec["probes"], spec["scoring"]
    db = MongoClient("mongodb://localhost:27017", tz_aware=True)["s9871_doc"]

    turn_rows, probe_rows, summary = [], [], []
    print("Sweep started", datetime.now().isoformat(timespec="seconds"), "| turns:", len(convo),
          "| configs:", args.configs, "| repeat:", args.repeat)
    base_settings = requests.get(f"{BASE}/api/settings").json()

    for label in args.configs.split(","):
        for rep in range(1, args.repeat + 1):
            user = f"{args.tag}_{label.lower()}_r{rep}"
            for coll in ("messages", "summaries", "episodes", "usage_log"):
                db[coll].delete_many({"user_id": user})
            seed = 9871 + rep - 1
            applied = requests.put(f"{BASE}/api/settings", json={**CONFIGS[label], "LLM_SEED": seed}).json()
            warm_up()
            print(f"\n=== {label} rep {rep} (user {user}) settings: "
                  f"POLICY={applied['POLICY']} N={applied['SHORT_TERM_N']} seed={seed} ===")
            session, t0 = None, time.perf_counter()
            run_turns = []
            for i, msg in enumerate(convo, 1):
                body = {"user_id": user, "message": msg}
                if session:
                    body["session_id"] = session
                d = post_chat(body)
                session = d["session_id"]
                u = d["usage"]
                row = {"setting": label, "repeat": rep, "turn": i,
                       "window_msgs": d["memory_used"]["short_term_count"],
                       "reply_prompt_tokens": u["prompt_tokens"],
                       "reply_completion_tokens": u["completion_tokens"],
                       "total_prompt_tokens": u["total_prompt_tokens"],
                       "total_completion_tokens": u["total_completion_tokens"],
                       "llm_calls": u["llm_calls"],
                       "reply_latency_ms": u["latency_ms"],
                       "request_latency_ms": u["request_latency_ms"],
                       **{f"tok_{c}": u["component_tokens"][c] for c in COMPONENTS}}
                run_turns.append(row)
                turn_rows.append(row)
                print(f"  turn {i:2d}: reply_prompt={row['reply_prompt_tokens']:4d} "
                      f"total_prompt={row['total_prompt_tokens']:5d} window={row['window_msgs']:2d} "
                      f"req_latency={row['request_latency_ms']:7.0f}ms")
            print(f"  conversation took {time.perf_counter() - t0:.0f}s")

            run_probes = []
            for pr in probes:
                d = post_chat({"user_id": user, "session_id": session,
                               "message": pr["question"], "read_only": True})
                sc = score_answer(d["reply"], pr, rubric)
                prow = {"setting": label, "repeat": rep, "probe": pr["id"],
                        "planted_at_turn": pr["planted_at_turn"], "question": pr["question"],
                        "expected": pr["expected_answer"], "answer": d["reply"],
                        "episodes_retrieved": [e["fact"] for e in d["memory_used"]["episodic_facts"]],
                        "had_session_summary": d["memory_used"]["session_summary"] is not None,
                        "had_lifetime_summary": d["memory_used"]["long_term_summary"] is not None,
                        **sc}
                run_probes.append(prow)
                probe_rows.append(prow)
                print(f"  {pr['id']} score={sc['score']} matched={sc['matched']} :: {d['reply'][:110]!r}")

            summary.append({
                "setting": label, "repeat": rep, "seed": seed, "config": CONFIGS[label],
                "mean_reply_prompt_tokens_per_turn": mean([r["reply_prompt_tokens"] for r in run_turns]),
                "mean_total_prompt_tokens_per_turn": mean([r["total_prompt_tokens"] for r in run_turns]),
                "mean_reply_completion_tokens_per_turn": mean([r["reply_completion_tokens"] for r in run_turns]),
                "mean_total_completion_tokens_per_turn": mean([r["total_completion_tokens"] for r in run_turns]),
                "mean_reply_latency_ms": mean([r["reply_latency_ms"] for r in run_turns]),
                "mean_request_latency_ms": mean([r["request_latency_ms"] for r in run_turns]),
                "mean_probe_score": mean([p["score"] for p in run_probes]),
                "probe_scores": {p["probe"]: p["score"] for p in run_probes},
                "mean_component_tokens": {c: mean([r[f"tok_{c}"] for r in run_turns]) for c in COMPONENTS},
            })
            print("  ->", {k: v for k, v in summary[-1].items() if k.startswith("mean_") and k != "mean_component_tokens"})

            # flush after every run so partial results survive an interruption
            with open(out / "part3_turns.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(turn_rows[0].keys()))
                w.writeheader(); w.writerows(turn_rows)
            (out / "part3_probes.json").write_text(json.dumps(probe_rows, indent=1, ensure_ascii=False), encoding="utf-8")
            (out / "part3_summary.json").write_text(json.dumps(
                {"generated": datetime.now().isoformat(timespec="seconds"), "seed": 9871,
                 "turns": len(convo), "runs": summary}, indent=1), encoding="utf-8")

    requests.put(f"{BASE}/api/settings", json={k: base_settings[k] for k in
                 ("POLICY", "SHORT_TERM_N", "COMPRESS_KEEP_LAST", "COMPRESS_SUMMARY_EVERY", "LLM_SEED")})
    print("\nSweep finished", datetime.now().isoformat(timespec="seconds"))


if __name__ == "__main__":
    sys.exit(main())
