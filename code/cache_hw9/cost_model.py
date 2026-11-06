"""
DATA-260 Homework 9 - Part 3.4: cost model for the threshold choice.

total cost over the 40 labeled cases = (cases not served from the cache) x C_MISS + (false hits) x C_FALSE

C_MISS  = 0.01 USD: a miss runs the HW8 pipeline = three qwen3 model calls (Planner, Writer, Reviewer) plus Kafka and the fact lookup.
          Locally that costs no cash but ~5.3 s of GPU time per question (Part 2); priced at an API-equivalent ~0.003 USD per call,
          3 calls ~ 0.01 USD. A hit costs ~0 (one embedding + one Redis search, ~12 ms), so a miss is the cost a cache hit saves.
C_FALSE = 2.50 USD: a false hit hands the user a confident WRONG fixture fact (wrong home team / ground / fixture name). The cost is a
          support contact: ~5 minutes of league-staff time at 30 USD/hour = 2.50 USD (not counting a player turning up at the wrong ground).
Both are assumptions, so sensitivity() recomputes the cheapest threshold for other C_FALSE values.
"""

C_MISS = 0.01
C_FALSE = 2.50


def total_cost(row: dict, c_miss: float = C_MISS, c_false: float = C_FALSE) -> float:
    return round(row["misses"] * c_miss + row["false_hits"] * c_false, 2)


def cheapest(thresholds: list[dict], c_false: float, c_miss: float = C_MISS) -> dict:
    return min(thresholds, key=lambda r: (total_cost(r, c_miss, c_false), -r["threshold"]))
