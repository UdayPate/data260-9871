"""
DATA-260 Homework 7 - Part 2: the hand-written agent loop (native tool calling, no framework).

run_agent(user_input) asks the model (through the HW1 adapter, ModelClient.chat) for its next move. If the model
asks for tools, each call is checked, executed through execute_tool (HW5: retry policy + the query-length safety
rule), and its result is appended as a TOOL-role message; the loop continues until the model gives a final
answer or a hard limit is hit.

A call is "invalid" if the tool name is unknown, the arguments are not a JSON object, or they break the tool's
JSON schema. An invalid call is NOT executed. Instead the model is re-prompted ONCE per attempt with a tool-role
message that names the specific problem and shows the schema. If the repair attempt is invalid again that is a
"failed repair"; after `max_failed_repairs` of them the run stops cleanly with stop_reason "repair_failed".

Stop reasons:  final_answer | max_steps | repair_failed | budget_exhausted
(max_tool_calls / max_total_tokens are optional budgets; Part 3's Reflexion wrapper uses them.)

Every emitted tool call is logged (tool name + inputs + whether it was valid + the outcome) to a JSONL file, and the
returned summary reports the totals.
"""

import json
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tool_schemas import TOOL_SPECS, ollama_tools, schema_hint, validate_call  # noqa: E402

DEFAULT_LOG_PATH = REPO_ROOT / "reports" / "hw07" / "raw" / "agent_runs.jsonl"

SYSTEM_PROMPT = """You are an assistant for a community sports league fixtures database.
Use the tools to look facts up. Never invent fixture ids, names, codes or numbers.
For a question that needs several steps, call the tools one after another until you have what you need,
then answer concisely using only what the tools returned.
If a tool returns ok=false, tell the user plainly what went wrong instead of guessing, and do not repeat the same impossible request."""


def quiet_noisy_loggers() -> None:
    """The HW5 domain code echoes every SQL statement; silence it so agent logs stay readable."""
    import logging

    for name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "domain", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        sys.path.insert(0, str(REPO_ROOT / "code" / "web_application"))
        from db import engine

        engine.echo = False
    except Exception:
        pass


def _short(value, limit=110):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def run_agent(
    user_input: str,
    model=None,
    *,
    max_steps: int = 8,
    max_failed_repairs: int = 2,
    max_tool_calls: int | None = None,
    max_total_tokens: int | None = None,
    tool_specs: dict | None = None,
    offered_specs: dict | None = None,
    executor=None,
    system_prompt: str = SYSTEM_PROMPT,
    log_path: Path | None = None,
    verbose: bool = False,
) -> dict:
    """Run the loop for one user request. Returns a summary dict (see the end of this function).

    model     - anything with .chat(messages, tools) -> reply dict (default: ModelClient with qwen3:8b, thinking off)
    executor  - callable(name, args) -> JSON string in the {ok, data, error} shape (default: HW5 execute_tool)
    offered_specs - what the MODEL is told about the tools (default: the same specs calls are validated against).
                    Only the Part 2 stress experiment sets it, to simulate schema drift.
    """
    specs = tool_specs or TOOL_SPECS
    if executor is None:
        from execute_tool import execute_tool

        quiet_noisy_loggers()
        executor = execute_tool
    if model is None:
        from model_client import ModelClient

        model = ModelClient(model="qwen3:8b", temperature=0.0, reasoning=False)
    log_path = Path(log_path) if log_path else DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    tools = ollama_tools(offered_specs or specs)
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}]
    trace: list[dict] = []        # one record per emitted tool call, in order
    counters = {"executed": 0, "invalid": 0, "rescued": 0, "failed_repairs": 0}
    tokens = {"prompt": 0, "completion": 0}
    latency_ms = 0.0
    started = time.perf_counter()
    pending: list[dict] = []      # invalid calls still waiting for a successful repair
    stop_reason, final_answer, step = None, None, 0

    def log(record: dict):
        with log_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"run_id": run_id, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}) + "\n")

    def say(text: str):
        if verbose:
            print(text, flush=True)

    while step < max_steps:
        if max_total_tokens is not None and tokens["prompt"] + tokens["completion"] >= max_total_tokens:
            stop_reason = "budget_exhausted"
            break
        step += 1
        reply = model.chat(messages, tools=tools)
        tokens["prompt"] += reply["usage"]["input_tokens"]
        tokens["completion"] += reply["usage"]["output_tokens"]
        latency_ms += reply.get("latency_ms", 0.0)

        # Every call the model emitted this turn: well-formed JSON ones, plus ones whose arguments were not JSON.
        emitted = [dict(c) for c in reply["tool_calls"]]
        for bad in reply.get("invalid_tool_calls", []):
            emitted.append({"id": bad.get("id"), "name": bad.get("name") or "", "args": bad.get("args")})
        for i, c in enumerate(emitted):
            c["id"] = c.get("id") or f"call_{run_id}_{step}_{i}"
        messages.append({"role": "assistant", "content": reply["content"], "tool_calls": emitted})

        if not emitted:                                    # plain text: the final answer
            final_answer, stop_reason = reply["content"].strip(), "final_answer"
            log({"kind": "final", "step": step, "answer": final_answer})
            say(f"[step {step}] FINAL ANSWER: {_short(final_answer, 200)}")
            break

        step_invalid, step_valid, budget_hit = [], 0, False
        for call in emitted:
            name, args = call["name"], call["args"]
            problem = validate_call(name, args, specs)
            # repair_attempt: this call came in the turn right after an invalid call (it is a retry, not a first try)
            record = {"step": step, "tool": name, "inputs": args, "valid": problem is None,
                      "failure_kind": problem[0] if problem else None, "repair_attempt": bool(pending)}
            if problem:
                kind, text = problem
                counters["invalid"] += 1
                record.update(problem=text, repaired=False)
                step_invalid.append(record)
                content = json.dumps({"ok": False, "data": None, "error": (
                    f"INVALID TOOL CALL ({kind}): {text}. Fix the call and try again. {schema_hint(name, specs)}")})
                say(f"[step {step}] CALL  {name} {_short(args)}  -> INVALID ({kind}): {_short(text, 80)}")
            else:
                if max_tool_calls is not None and counters["executed"] >= max_tool_calls:
                    budget_hit = True
                    break
                content = executor(name, args)
                counters["executed"] += 1
                envelope = json.loads(content)
                record.update(ok=envelope["ok"], error=envelope.get("error"))
                step_valid += 1
                say(f"[step {step}] CALL  {name} {_short(args)}  -> "
                    f"{'ok' if envelope['ok'] else 'ERROR: ' + _short(envelope.get('error'), 70)}")
            trace.append(record)
            log({"kind": "tool_call", **record})
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": content})
        if budget_hit:
            stop_reason = "budget_exhausted"
            break

        # Repair accounting: the turn right after an invalid call is the repair attempt.
        if pending:
            if step_invalid:
                counters["failed_repairs"] += 1
                if counters["failed_repairs"] >= max_failed_repairs:
                    stop_reason = "repair_failed"
                    pending.extend(step_invalid)
                    break
            elif step_valid:
                for rec in pending:
                    rec["repaired"] = True
                counters["rescued"] += len(pending)
                pending = []
        if step_invalid:
            pending = pending + step_invalid if pending else step_invalid

    if stop_reason is None:
        stop_reason = "max_steps"
    summary = {
        "run_id": run_id,
        "user_input": user_input,
        "stop_reason": stop_reason,
        "steps": step,
        "tool_calls_total": counters["executed"] + counters["invalid"],
        "tool_calls_executed": counters["executed"],
        "tool_calls_invalid": counters["invalid"],
        "invalid_calls_repaired": counters["rescued"],
        "failed_repairs": counters["failed_repairs"],
        "final_answer": final_answer,
        "tokens": dict(tokens),
        "latency_ms": round(latency_ms, 1),
        "wall_ms": round((time.perf_counter() - started) * 1000, 1),
        "trace": trace,
        "messages": messages,
    }
    log({"kind": "run_summary", **{k: v for k, v in summary.items() if k not in ("trace", "messages")}})
    say(f"[done] stop_reason={stop_reason} steps={step} total tool calls={summary['tool_calls_total']} "
        f"(executed {counters['executed']}, invalid {counters['invalid']}, repaired {counters['rescued']}) "
        f"tokens={tokens['prompt'] + tokens['completion']}")
    summary["log_path"] = str(log_path)
    return summary


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Search for fixtures matching 'Lions' and give me the full details of the first result."
    out = run_agent(q, verbose=True)
    print("\nFinal answer:\n" + (out["final_answer"] or f"(no final answer: {out['stop_reason']})"))
