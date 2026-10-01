"""
DATA-260 Homework 5 - Part 5.II: agent loop over the three domain tools,
using the local Ollama model via src/model_client.py's ModelClient (the
same adapter from HW1-2, reused rather than calling Ollama directly).

run_agent(user_input) asks the model, each turn, to either call one of the
three domain tools (through execute_tool, so the Part 5 safety rule and
Part 3 retry policy both apply) or give a final answer. It stops on:
  - "final_answer"       - the model gave a final answer (normal completion)
  - "safety_rule_block"  - a tool call was rejected by the Part 5.I rule
  - "max_steps_ceiling"  - max_steps reached with no final answer

Every step (tool call, input, result) and the final stop reason are logged
to agent_runs.jsonl, one JSON object per line.
"""

import json
import re
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_tool import TOOLS, execute_tool  # noqa: E402

DEFAULT_LOG_PATH = REPO_ROOT / "reports" / "hw05" / "raw" / "agent_runs.jsonl"

TOOL_DESCRIPTIONS = """\
- search_fixtures(query: string, limit: int = 10) - search fixtures by name
  or teams_players. query must be at least 3 characters.
- fixture_details(id: int) - full details of one fixture by id, including
  its home team.
- team_fixture_counts(min_fixtures: int = 0) - number of fixtures hosted by
  each team, optionally filtered to teams with at least min_fixtures."""

SYSTEM_PROMPT = f"""You are an assistant for a community sports league fixtures database.
You can call these tools:
{TOOL_DESCRIPTIONS}

On every turn, respond with EXACTLY ONE JSON object and nothing else - no
markdown fences, no explanation outside the JSON. Use one of these two
shapes:
  {{"action": "tool", "tool": "<tool name>", "inputs": {{...}}}}
  {{"action": "final", "answer": "<your answer to the user>"}}
"""


class MockModel:
    """Test double for the offline max_steps test (Part 5.III). Always
    asks for another tool call, so run_agent is guaranteed to exhaust
    max_steps - never a live model, no network, fully deterministic."""

    def complete(self, messages, tools=None):
        return json.dumps({"action": "tool", "tool": "team_fixture_counts", "inputs": {}})


def _extract_json(text: str) -> dict | None:
    """Models (especially 'thinking' ones) often wrap JSON in prose or
    <think> blocks. Pull out the first balanced {...} object instead of
    assuming the whole string is clean JSON."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def run_agent(
    user_input: str,
    model=None,
    max_steps: int = 5,
    tools: dict | None = None,
    log_path: Path | None = None,
) -> dict:
    """Run the agent loop. Returns a summary dict: stop_reason, steps,
    tool_call_count, final_answer (if any), run_id, log_path."""
    if model is None:
        from model_client import ModelClient
        model = ModelClient(model="qwen3:8b", temperature=0.0)

    log_path = log_path or DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    def log(record: dict):
        record = {"run_id": run_id, **record}
        with log_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record) + "\n")

    tool_call_count = 0
    stop_reason = None
    final_answer = None
    step = 0

    while step < max_steps:
        step += 1
        raw = model.complete(messages)
        messages.append({"role": "assistant", "content": raw})

        parsed = _extract_json(raw)
        if parsed is None:
            # Model didn't follow the protocol - treat its raw text as the
            # final answer rather than crashing the loop.
            final_answer = raw.strip()
            stop_reason = "final_answer"
            log({"step": step, "tool": None, "inputs": None, "result": None,
                 "note": "unparseable model output, treated as final answer"})
            break

        if parsed.get("action") == "final":
            final_answer = parsed.get("answer", "")
            stop_reason = "final_answer"
            log({"step": step, "tool": None, "inputs": None, "result": None,
                 "final_answer": final_answer})
            break

        if parsed.get("action") == "tool":
            tool_name = parsed.get("tool")
            tool_inputs = parsed.get("inputs") or {}
            result = json.loads(execute_tool(tool_name, tool_inputs, tools=tools))
            tool_call_count += 1
            log({"step": step, "tool": tool_name, "inputs": tool_inputs, "result": result})

            if not result.get("ok") and "query too broad" in (result.get("error") or ""):
                stop_reason = "safety_rule_block"
                break

            messages.append({
                "role": "user",
                "content": f"Tool result for {tool_name}: {json.dumps(result)}",
            })
            continue

        # Unrecognized action - same fallback as unparseable output.
        final_answer = raw.strip()
        stop_reason = "final_answer"
        log({"step": step, "tool": None, "inputs": None, "result": None,
             "note": f"unrecognized action {parsed.get('action')!r}"})
        break

    if stop_reason is None:
        stop_reason = "max_steps_ceiling"

    summary = {
        "run_id": run_id,
        "user_input": user_input,
        "stop_reason": stop_reason,
        "steps": step,
        "tool_call_count": tool_call_count,
        "final_answer": final_answer,
    }
    log({"final": True, **{k: v for k, v in summary.items() if k != "run_id"}})
    summary["log_path"] = str(log_path)
    return summary


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "How many fixtures does Milpitas Lions host?"
    print(json.dumps(run_agent(q, max_steps=5), indent=2))
