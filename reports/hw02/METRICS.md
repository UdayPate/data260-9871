# METRICS — HW2 Part 4: Output Schema and Loop Safety

## Experiment 1: 30-run classification (fixed input, turn_ceiling=6)

Fixed input: `reports/hw02/cases/schema_input.json` (San Jose Strikers vs
Milpitas Warriors cricket rivalry fixture, same input used in HW1 Part 3).

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---|---|
| Valid first attempt | 25 | 35,777.8 |
| Valid after 1 retry | 4 | 80,595.1 |
| Valid after 2+ retries | 0 | — |
| Hit turn ceiling | 1 | 81,672.1 |

**Observation:** 29 of 30 runs (96.7%) reached a valid, reviewed output.
No run ever needed more than one retry to satisfy both the Pydantic
schema and the Reviewer's checks — when a correction was needed, it was
resolved on the very next Planner attempt. Runs that needed a retry took
roughly 2.25x longer than first-attempt successes (80.6s vs 35.8s),
which is the direct cost of the extra Planner+Reviewer round trip.

## Experiment 2: Turn ceiling comparison (20 runs each, same fixed input)

| Metric | Ceiling = 2 | Ceiling = 10 |
|---|---|---|
| Completion rate | 0% (0/20) | 100% (20/20) |
| Mean latency (ms) | 17,526.5 | 46,256.8 |

**Observation:** `turn_ceiling=2` failed on every single run, not due to
model quality but by construction: the Supervisor node increments
`turn_count` on every visit, including its very first entry and its
check-in immediately after Planner's first attempt. By the time
Supervisor re-evaluates after Planner's first proposal, `turn_count`
already equals 2, forcing an immediate END before the Reviewer node
ever runs once. `turn_ceiling=2` is structurally incapable of completing
even a single successful Planner-then-Reviewer cycle in this graph
design.

**Deployment choice:** Based on this data, **turn_ceiling=10** (or any
value ≥ 6, per Experiment 1's results) should be used for deployment.
`turn_ceiling=2` is not viable — it guarantees 0% completion regardless
of how well the model performs. A ceiling of 6-10 gives enough headroom
for the single-retry corrections that account for the vast majority of
non-first-attempt successes observed in Experiment 1, while still
bounding worst-case latency.

## Experiment 3: Adversarial input (5 runs, turn_ceiling=6)

Adversarial input: `reports/hw02/cases/adversarial_input.json`
(title: "Match", content: "A game happened. It was fine.") — chosen for
its near-total lack of concrete, specific information to derive tags
from.

| Outcome over 5 runs | Count |
|---|---|
| Hit turn ceiling | 2 (40%) |
| Success | 3 (60%) |

**Observation:** This did not reach the ceiling in 4+ of 5 runs, so per
the assignment's instructions this reports the observed rate (40%)
rather than claiming deterministic failure. The adversarial input was
nonetheless clearly harder than the normal fixed input: the Reviewer
intervened at least once in 4 of the 5 runs here (80%), compared to only
5 of 30 runs (16.7%) on the normal fixture in Experiment 1. In the 3
runs that eventually succeeded, the Planner often converged on
technically-valid but still fairly generic tags (e.g. "game event",
"match outcome", "neutral assessment") to satisfy the Reviewer, rather
than genuinely specific ones — because the input itself contains no
specific entities, teams, locations, or details to draw from.

**Why this input causes trouble:** the Reviewer's instructions ask for
tags that are "genuinely specific to the content," but this input has no
specific content — no team names, no location, no distinguishing detail.
The Planner is caught between two failure modes: producing honestly
generic tags (which the Reviewer correctly rejects as too vague) or
inventing specific-sounding but ungrounded details (which risks
inaccuracy). This is a genuine limitation of the pipeline, not a bug: it
assumes the input contains enough real information to tag specifically,
and vague inputs violate that assumption.

**Proposed fix:** add an input-validation step before the graph even
starts — e.g., a minimum content length or a check for the presence of
at least one proper noun/specific entity — and short-circuit with a
clear "insufficient detail provided" message rather than letting the
Planner/Reviewer loop repeatedly attempt to extract specificity that
was never there to begin with.