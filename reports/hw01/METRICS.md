# METRICS — HW1 Part 3: Measuring Non-Determinism

## Tag Set Variation

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Distinct tag sets | 13 | 1 |
| Tags in all 20 runs | (none) | bay area rivalry, cricket match, team rivalry |
| Tags in exactly 1 run | bay area, fast bowling, game strategy, green pitch, league title race, middle order, strategic play, team rivalry, team standings, team strategies, top league teams | (none) |

## Latency

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Latency p50 (ms) | 49282.5 | 48720.5 |
| Latency p95 (ms) | 72209.5 | 49382.9 |
| Latency p99 (ms) | 79907.2 | 49721.1 |

## Observations

At temperature 0.0, the pipeline produced identical tags across all 20 runs, confirming qwen3:8b is effectively deterministic at this setting. At temperature 0.7, only 13 of 20 runs produced a unique tag combination, and no single tag appeared in every run even "bay area rivalry" and "cricket match," which appeared in 19/20 runs, each had one outlier run. Latency was also far more consistent at temp 0.0 (a ~1 second range) than at temp 0.7 (a ~57 second range), suggesting the added randomness affects not just word choice but how much the model "explores" before settling on an answer.