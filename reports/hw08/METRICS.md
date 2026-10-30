# HW8 METRICS

Part 3 failure tests: every number below is read from `raw/part3_*.json`; each "before" and "after" is a real run of the
same Writer code (`HW8_MODE=naive` vs `HW8_MODE=fixed`). The Writer ran in its model-free `WRITER_MODE=stub` so the
tests are fast; the Part 2 journey used the real qwen3:8b. SEED = 9871, VERIFY_SEED = 269871.

## Part 3 - failure table

| Failure scenario | Before fix (naive) | After fix |
|---|---|---|
| Duplicate delivery | one correlation_id replayed -> 2 deliveries, 2 work executions, **2 drafts** in `s9871_drafts` | same replay -> 2 deliveries, 1 work execution, 1 `DUPLICATE ... skipped`, **1 draft** |
| Consumer killed mid-work | offset committed *before* processing: after the kill committed offset = 1, lag 0; after restart redelivered = False, drafts = **0** (message silently lost) | offset committed *after* success: after the kill committed offset = None; after restart redelivered = True, drafts = **1**, then committed offset = 1 (lag 0) |
| Poison message | retried **29+ times without limit**; good message behind it processed = False; consumer-group lag = 2 | **3 attempts**, then 1 message in `s9871_dead_letter` (attempts field = 3); good message processed = True; lag 0 |
| Two partitions / two consumers | no key: 3 of 4 entities processed out of order (12 inversions); 3 entities split across both partitions | key = entity_id: 0 entities out of order (0 inversions); 0 entities split across partitions |

## Part 3 IV - ordering detail (20 messages, VERIFY_SEED 269871, 2 partitions, Writers A and B)

Per entity, `processed order` is the entity_seq values in the order the Writers finished them (1,2,3... would be correct).

| Entity | Messages | No key: processed order | No key: partitions / writers | Keyed: processed order | Keyed: partition / writer |
|---|---|---|---|---|---|
| FX-9871-101 | 1 | [1] | [1] / ['B'] | [1] | [1] / ['B'] |
| FX-9871-102 | 4 | [1, 3, 2, 4] | [0, 1] / ['A', 'B'] | [1, 2, 3, 4] | [1] / ['B'] |
| FX-9871-103 | 8 | [2, 1, 6, 7, 3, 4, 5, 8] | [0, 1] / ['A', 'B'] | [1, 2, 3, 4, 5, 6, 7, 8] | [1] / ['B'] |
| FX-9871-104 | 7 | [1, 2, 3, 6, 7, 4, 5] | [0, 1] / ['A', 'B'] | [1, 2, 3, 4, 5, 6, 7] | [0] / ['A'] |

## What the numbers show

- **Duplicate delivery.** With no idempotency, replaying one correlation_id made the Writer do the work twice and emit
  2 drafts, so everything downstream (Reviewer, final answer) would also run twice. With the
  processed-correlation_id store the second delivery is logged as a duplicate and produces no output and no side effect.
  The replay is still read and its offset committed, so lag returns to 0.
- **Consumer death.** Committing the offset *before* the work is at-most-once: the Writer was killed 1.5 s into an 8 s job,
  the broker already believed the message was handled (committed offset 1, lag 0), and after the restart nothing
  arrived - the message was lost with no error anywhere. Committing *after* the draft is delivered leaves the offset uncommitted
  at the kill (None), so the restarted Writer received the same offset again, finished it and only then committed.
  The price of at-least-once is that work can run twice (the kill happened mid-job), which is exactly why the
  idempotency store is needed alongside it. One small window remains: a crash between delivering the draft and recording
  the correlation_id can still produce one duplicate draft; closing it fully needs Kafka transactions, which this exercise does not use.
- **Poison message.** An unprocessable message with unbounded retry stays at the head of its partition forever: 29 attempts
  in 15 s and the valid message behind it never ran (lag 2). With 3 attempts and a dead-letter topic the bad message is
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
