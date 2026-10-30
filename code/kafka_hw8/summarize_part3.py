"""Writes reports/hw08/METRICS.md (Part 1 and 2 notes, Part 3 tables) from the saved raw/part3_*.json (no numbers typed by hand)."""

import json
from pathlib import Path

HW = Path(__file__).resolve().parents[2] / "reports" / "hw08"
load = lambda n: json.loads((HW / "raw" / f"part3_{n}.json").read_text(encoding="utf-8"))  # noqa: E731
dn, df, kn, kf, pn, pf, ou, ok = (load(n) for n in (
    "duplicate_naive", "duplicate_fixed", "kill_naive", "kill_fixed", "poison_naive", "poison_fixed",
    "ordering_unkeyed", "ordering_keyed"))
c = lambda d: "none" if d["after_kill"]["committed"]["0"] is None else d["after_kill"]["committed"]["0"]  # noqa: E731

# Part 2 timings come from the saved journey (all stages ran on the Windows host, so one clock)
from datetime import datetime  # noqa: E402

journey = [ln for ln in (HW / "raw" / "part2_journey.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
at = lambda i: datetime.strptime(journey[i][:23], "%Y-%m-%d %H:%M:%S.%f")  # noqa: E731
stage = {n: (at(i + 2) - at(i)).total_seconds() for n, i in (("Planner", 1), ("Writer", 4), ("Reviewer", 7))}  # RECEIVED -> SENT
total = (at(-1) - at(0)).total_seconds()

text = f"""# HW8 METRICS

Part 3 failure tests: every number below is read from `raw/part3_*.json`; each "before" and "after" is a real run of the
same Writer code (`HW8_MODE=naive` vs `HW8_MODE=fixed`). The Writer ran in its model-free `WRITER_MODE=stub` so the
tests are fast; the Part 2 journey used the real qwen3:8b. SEED = {dn['SEED']}, VERIFY_SEED = {dn['VERIFY_SEED']}.

## Part 1 - notes

- **Kafka client: `confluent-kafka` 2.16.1.** It is Confluent's own, actively released client over librdkafka, ships prebuilt wheels for both Windows (where the demo and agents run) and the Linux `python:3.12-slim` image (worker and API), and gives the manual offset commits, explicit partitions/keys and clean consumer-group leave that Part 3 needs. `kafka-python` is rarely updated and `aiokafka` would have made the synchronous worker harder to control.
- **Entity and storage.** The primary entity is Fixture (domain 7) with the six fields of `DOMAIN_SCHEMA.md`. The worker keeps entities in a plain Python dict, so they are lost when the worker restarts (a GET after a restart answers `Entity not found`); that is what the assignment asks for.
- **Timestamps.** The worker runs in the Docker VM and the client on Windows, and their clocks disagree (by tens of milliseconds in some runs and about 0.3 s in others), so the client's "response received" line can carry an earlier time than the worker's "request received" line. `homework_demo.py` therefore prints each request's lines in causal order and the Kafka offsets in every line show the order.

## Part 2 - how Kafka helped the agents coordinate

Planner, Writer and Reviewer are three separate processes that never call each other; each only reads one topic and writes the next one (`s9871_inbox` -> `s9871_tasks` -> `s9871_drafts` -> `s9871_final`). One real question took {total:.1f} s end to end with qwen3:8b (Planner {stage['Planner']:.1f} s, Writer {stage['Writer']:.1f} s, Reviewer {stage['Reviewer']:.1f} s), and the same correlation_id is on every message from the question to the final answer.

- **Decoupling.** An agent only needs the topic names, not the address or API of the next agent. A stage that is down does not lose work: its input waits in the topic and is read when it comes back (shown for the Writer in Part 3).
- **Scaling.** `s9871_tasks` has two partitions, so two Writers in one consumer group split the work with no change to the Writer's code (Part 3, ordering).
- **Durable hand-offs and offsets.** Every hand-off is a persisted, replayable message, and each agent commits its input offset only after its output is delivered, so a crash causes a re-read, not a lost message.
- **Correlation.** The correlation_id lets the final answer be matched to the question without any shared state between the agents.

## Part 3 - failure table

| Failure scenario | Before fix (naive) | After fix |
|---|---|---|
| Duplicate delivery | one correlation_id replayed -> {dn['deliveries_received']} deliveries, {dn['writer_work_executions']} work executions, **{dn['drafts_in_output_topic']} drafts** in `s9871_drafts` | same replay -> {df['deliveries_received']} deliveries, {df['writer_work_executions']} work execution, {df['duplicate_skips_logged']} `DUPLICATE ... skipped`, **{df['drafts_in_output_topic']} draft** |
| Consumer killed mid-work | offset committed *before* processing: after the kill committed offset = {c(kn)}, lag {kn['final_lag']['0']['lag']}; after restart redelivered = {kn['redelivered_after_restart']}, drafts = **{kn['drafts_in_output_topic']}** (message silently lost) | offset committed *after* success: after the kill committed offset = {c(kf)}; after restart redelivered = {kf['redelivered_after_restart']}, drafts = **{kf['drafts_in_output_topic']}**, then committed offset = {kf['final_lag']['0']['committed']} (lag {kf['final_lag']['0']['lag']}) |
| Poison message | retried **{pn['poison_attempts_logged']}+ times without limit**; good message behind it processed = {pn['good_message_processed']}; consumer-group lag = {pn['lag']['0']['lag']} | **{pf['poison_attempts_logged']} attempts**, then {pf['dead_letter_messages_for_poison']} message in `s9871_dead_letter` (attempts field = {pf['dead_letter_attempts_field'][0]}); good message processed = {pf['good_message_processed']}; lag {pf['lag']['0']['lag']} |
| Two partitions / two consumers | no key: {ou['entities_out_of_order']} of {len(ou['per_entity'])} entities processed out of order ({ou['total_inversions']} inversions); {ou['entities_split_across_partitions']} entities split across both partitions | key = entity_id: {ok['entities_out_of_order']} entities out of order ({ok['total_inversions']} inversions); {ok['entities_split_across_partitions']} entities split across partitions |

## Part 3 IV - ordering detail (20 messages, VERIFY_SEED {ou['VERIFY_SEED']}, 2 partitions, Writers A and B)

Per entity, `processed order` is the entity_seq values in the order the Writers finished them (1,2,3... would be correct).

| Entity | Messages | No key: processed order | No key: partitions / writers | Keyed: processed order | Keyed: partition / writer |
|---|---|---|---|---|---|
"""
for e in ou["per_entity"]:
    u, k = ou["per_entity"][e], ok["per_entity"][e]
    text += (f"| {e} | {u['messages']} | {u['processed_in_seq_order']} | {u['partitions']} / {u['writers']} "
             f"| {k['processed_in_seq_order']} | {k['partitions']} / {k['writers']} |\n")

text += f"""
## What the numbers show

- **Duplicate delivery.** With no idempotency, replaying one correlation_id made the Writer do the work twice and emit
  {dn['drafts_in_output_topic']} drafts, so everything downstream (Reviewer, final answer) would also run twice. With the
  processed-correlation_id store the second delivery is logged as a duplicate and produces no output and no side effect.
  The replay is still read and its offset committed, so lag returns to 0.
- **Consumer death.** Committing the offset *before* the work is at-most-once: the Writer was killed 1.5 s into an 8 s job,
  the broker already believed the message was handled (committed offset {c(kn)}, lag 0), and after the restart nothing
  arrived - the message was lost with no error anywhere. Committing *after* the draft is delivered leaves the offset uncommitted
  at the kill ({c(kf)}), so the restarted Writer received the same offset again, finished it and only then committed.
  The price of at-least-once is that work can run twice (the kill happened mid-job), which is exactly why the
  idempotency store is needed alongside it. One small window remains: a crash between delivering the draft and recording
  the correlation_id can still produce one duplicate draft; closing it fully needs Kafka transactions, which this exercise does not use.
- **Poison message.** An unprocessable message with unbounded retry stays at the head of its partition forever: {pn['poison_attempts_logged']} attempts
  in 15 s and the valid message behind it never ran (lag {pn['lag']['0']['lag']}). With 3 attempts and a dead-letter topic the bad message is
  parked with its error, original bytes and source offset, and the next message completed immediately.
  (The naive poison run keeps commit-after so that only the retry policy differs from the fixed run.)
- **Ordering.** Kafka only orders messages *within a partition*. Without a key the 20 messages were spread over both
  partitions and two Writers raced, so related messages for the same fixture finished out of order. Keying by entity_id sends every
  message for a fixture to one partition, hence to one Writer, and the order was preserved for all entities
  (the keyed run also shows the cost: one Writer handles the busiest fixture on its own).

## Part 3 V - comparison with the HW2 in-process graph

`code/agent_graph.py` (HW2) is a LangGraph `StateGraph`: Supervisor, Planner and Reviewer are Python functions called one after
another in a single process. They share one in-memory `AgentState` dict (including the live model client), the router
(`router_logic`) reads that state to decide the next node, a `turn_ceiling` of 6 bounds the loop, and a failed Pydantic
validation is retried by routing back to the Planner. Every step waits for the previous function to return.

**Two benefits of moving to Kafka**

1. *Independent scaling.* In HW2 the only way to do more work is a faster process. Here `s9871_tasks` has 2 partitions and two
   Writer instances in one consumer group shared the 20 messages (Part 3 IV: Writer A held partition 0, Writer B partition 1) without any
   change to the Writer code.
2. *Decoupled failure and time.* In HW2 an exception inside any node ends the whole run and the in-memory state is gone. Here the
   Writer was killed mid-job and the message was still waiting in the topic; the restarted Writer finished it (Part 3 II),
   and a poison message is parked in `s9871_dead_letter` instead of stopping the pipeline. Planner, Writer and Reviewer can also be
   stopped and restarted separately because they only share topics.

**Two new responsibilities**

1. *Duplicate delivery / idempotency.* A function call runs exactly once. Kafka is at-least-once, so a redelivery or replay runs the
   Writer again; I had to add a durable processed-correlation_id store (and commit offsets only after success) to keep the side effect single.
2. *Ordering.* The HW2 graph's order is decided by its router and is always the same. Kafka guarantees order only inside a
   partition, so I had to choose a message key (entity_id) to keep related messages in order; anything keyed badly (or unkeyed) is
   reordered across consumers. Related to this, I now own the retry limit and the dead-letter policy that HW2 handled with `turn_ceiling`.

One honest difference: HW2's Reviewer could send work back to the Planner (feedback loop). The Part 2 pipeline is one-way
(Reviewer only approves or rejects), so that self-correction loop is not reproduced here.
"""
(HW / "METRICS.md").write_text(text, encoding="utf-8")
print(text[:1800])
