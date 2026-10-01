# Reflection (Part 5.V)

Run picked from `reports/hw05/raw/agent_runs.jsonl`: `run_id 45743a9ea8d1`,
user input "Look up fixture id 10 and summarize it for me.", `max_steps=1`.

On turn 1, `run_agent` sent the system prompt (the three domain tools plus
the required JSON response format) and the question to qwen3:8b via
`ModelClient`. The model replied with
`{"action": "tool", "tool": "fixture_details", "inputs": {"id": 10}}`,
correctly recognizing the question needed a tool call, not a guess.
`run_agent` parsed that JSON and ran `fixture_details(id=10)` through
`execute_tool`, wrapped in Part 3's retry/timeout policy. The call
succeeded on the first attempt, returning the real row: "Bears vs Panthers
(Volleyball #8)", code FX-9871-00010, 22 spots available, home team Santa
Clara Bears. That `{ok: true, data: {...}}` envelope was logged as the
step record and appended to the conversation for the model's next turn.

That is where the run stopped. `max_steps` was deliberately set to 1, so
`while step < max_steps` was already false after the one turn that
produced the tool call - no second turn remained for the model to read the
result and write a summary. `run_agent` exits the loop, finds no final
answer and no safety-rule block, and falls back to
`stop_reason = "max_steps_ceiling"`. The final log record shows exactly
this: `tool_call_count: 1`, `steps: 1`, `final_answer: null` - the agent
had the right data but ran out of turns before reporting it.

This illustrates why `max_steps` matters even when nothing goes wrong: a
correctly-behaving agent can still hit a step budget too low for the task.
This question needed at least two turns - call the tool, then read the
result back - and `max_steps=1` wasn't enough by design. The harness
stopped cleanly rather than looping forever or guessing without the data
it had just fetched.
