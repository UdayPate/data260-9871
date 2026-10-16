"""
DATA-260 Homework 6 - Part 3 analysis. Reads ONLY the raw result files written by
run_part3_sweep.py (reports/hw06/raw/part3_*.json|csv) and produces the results
tables + the 10,000-conversation cost estimate (raw/part3_cost.json).
Pricing (from the assignment): $1 per 1M input tokens, $5 per 1M output tokens.
Best/worst rule (fixed before the sweep): worst = most expensive setting;
best = cheapest setting whose mean probe score is within 0.5 of the highest score.
"""

import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw"
PRICE_IN, PRICE_OUT = 1.0 / 1e6, 5.0 / 1e6
CONVOS, TURNS = 10_000, 30
ORDER = ["N4", "N12", "N30", "COMPRESS"]
LABEL = {"N4": "SHORT_TERM_N=4", "N12": "SHORT_TERM_N=12", "N30": "SHORT_TERM_N=30",
         "COMPRESS": "Compression policy (keep last 6 + summary every 3)"}

rows = list(csv.DictReader(open(RAW / "part3_turns.csv", encoding="utf-8")))
probes = json.load(open(RAW / "part3_probes.json", encoding="utf-8"))
runs = json.load(open(RAW / "part3_summary.json", encoding="utf-8"))["runs"]

by_setting = defaultdict(list)
for r in rows:
    by_setting[r["setting"]].append(r)


def col(setting, key):
    return [float(r[key]) for r in by_setting[setting]]


def per_run_means(setting, key):
    g = defaultdict(list)
    for r in by_setting[setting]:
        g[r["repeat"]].append(float(r[key]))
    return [st.fmean(v) for v in g.values()]


summ = {}
for s in ORDER:
    scores = [p["score"] for p in probes if p["setting"] == s]
    per_run = defaultdict(list)
    for p in probes:
        if p["setting"] == s:
            per_run[p["repeat"]].append(p["score"])
    d = {
        "n_turns": len(by_setting[s]),
        "n_runs": len({r["repeat"] for r in by_setting[s]}),
        "mean_reply_prompt_tokens": st.fmean(col(s, "reply_prompt_tokens")),
        "mean_total_prompt_tokens": st.fmean(col(s, "total_prompt_tokens")),
        "mean_reply_completion_tokens": st.fmean(col(s, "reply_completion_tokens")),
        "mean_total_completion_tokens": st.fmean(col(s, "total_completion_tokens")),
        "mean_reply_latency_ms": st.fmean(col(s, "reply_latency_ms")),
        "mean_request_latency_ms": st.fmean(col(s, "request_latency_ms")),
        "mean_probe_score": st.fmean(scores),
        "probe_score_per_run": [round(st.fmean(v), 2) for v in per_run.values()],
        "reply_prompt_range_across_runs": [round(min(per_run_means(s, "reply_prompt_tokens")), 1),
                                           round(max(per_run_means(s, "reply_prompt_tokens")), 1)],
        "components": {c: st.fmean(col(s, f"tok_{c}")) for c in
                       ["system_primer", "long_term_summary", "short_term_window",
                        "episodic_facts", "current_message", "template_overhead"]},
    }
    # cost of 10,000 30-turn conversations, counting EVERY model call made
    # (reply + episode extraction + summarisation), and reply-only for reference
    per_turn_all = d["mean_total_prompt_tokens"] * PRICE_IN + d["mean_total_completion_tokens"] * PRICE_OUT
    per_turn_reply = d["mean_reply_prompt_tokens"] * PRICE_IN + d["mean_reply_completion_tokens"] * PRICE_OUT
    d["cost_10k_convos_all_calls_usd"] = per_turn_all * TURNS * CONVOS
    d["cost_10k_convos_reply_only_usd"] = per_turn_reply * TURNS * CONVOS
    summ[s] = d

top = max(v["mean_probe_score"] for v in summ.values())
eligible = [s for s in ORDER if summ[s]["mean_probe_score"] >= top - 0.5]
best = min(eligible, key=lambda s: summ[s]["cost_10k_convos_all_calls_usd"])
worst = max(ORDER, key=lambda s: summ[s]["cost_10k_convos_all_calls_usd"])

print("=== Part 3 results table (means over %d turns x %d runs per setting) ===" % (summ["N4"]["n_turns"] // 3, 3))
print(f"{'Setting':58s} {'prompt tok/turn':>16s} {'total prompt':>13s} {'req latency ms':>15s} {'reply lat ms':>13s} {'probe 1-5':>10s}")
for s in ORDER:
    v = summ[s]
    print(f"{LABEL[s]:58s} {v['mean_reply_prompt_tokens']:16.1f} {v['mean_total_prompt_tokens']:13.1f} "
          f"{v['mean_request_latency_ms']:15.0f} {v['mean_reply_latency_ms']:13.0f} {v['mean_probe_score']:10.2f}")
print("\nprobe score per seed run:", {s: summ[s]["probe_score_per_run"] for s in ORDER})
print("reply-prompt-token range across the 3 seed runs:", {s: summ[s]["reply_prompt_range_across_runs"] for s in ORDER})

print("\n=== Mean prompt-token breakdown per turn (reply call) ===")
print(f"{'Setting':10s} " + " ".join(f"{c:>18s}" for c in summ["N4"]["components"]))
for s in ORDER:
    print(f"{s:10s} " + " ".join(f"{v:18.1f}" for v in summ[s]["components"].values()))

b = summ["N30"]
print("\n=== Savings of the compression policy vs the full-history baseline (N=30) ===")
c = summ["COMPRESS"]
for k, name in [("mean_reply_prompt_tokens", "reply prompt tokens/turn"), ("mean_total_prompt_tokens", "all-call prompt tokens/turn")]:
    print(f"  {name}: {b[k]:.1f} -> {c[k]:.1f}  ({(1 - c[k] / b[k]) * 100:.1f}% saved)")
print(f"  probe quality: {b['mean_probe_score']:.2f} -> {c['mean_probe_score']:.2f}")
n4 = summ["N4"]
print("  vs N=4 for reference: reply prompt tokens %.1f vs %.1f, probe %.2f vs %.2f"
      % (c["mean_reply_prompt_tokens"], n4["mean_reply_prompt_tokens"], c["mean_probe_score"], n4["mean_probe_score"]))

print("\n=== Estimated cost of 10,000 x 30-turn conversations (input $1/M, output $5/M) ===")
print(f"{'Setting':58s} {'all model calls':>16s} {'reply call only':>16s}")
for s in ORDER:
    v = summ[s]
    print(f"{LABEL[s]:58s} ${v['cost_10k_convos_all_calls_usd']:14,.2f} ${v['cost_10k_convos_reply_only_usd']:14,.2f}")
print(f"\nRule: worst = most expensive; best = cheapest with mean probe score >= top({top:.2f}) - 0.5.")
print(f"Eligible for best: {eligible}  ->  BEST = {best} (${summ[best]['cost_10k_convos_all_calls_usd']:,.2f}),"
      f"  WORST = {worst} (${summ[worst]['cost_10k_convos_all_calls_usd']:,.2f})")

json.dump({"pricing_usd_per_token": {"input": PRICE_IN, "output": PRICE_OUT},
           "conversations": CONVOS, "turns_per_conversation": TURNS, "best": best, "worst": worst,
           "eligible_for_best": eligible, "settings": summ},
          open(RAW / "part3_cost.json", "w", encoding="utf-8"), indent=1)
