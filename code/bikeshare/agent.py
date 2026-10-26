"""
DATA-260 Homework 7 - Part 4: the framework ReAct/MRKL agent that recommends monthly membership vs pay-per-use.

The agent is built with LangChain's create_agent (a LangGraph ReAct loop: model -> tools -> model ...) on qwen3:8b through Ollama,
with the three tools from tools.py. run_bike_agent() streams the graph, records a timeline of tool calls and observations, parses
the final JSON answer (one repair re-prompt if it is not valid), then ATTACHES the evidence the model cannot supply itself:
the pricing snapshot (URL, access time, SHA-256), whether each quoted citation really appears in that snapshot, and an independent
recomputation of the costs from the CSV (costs.py) so a wrong answer is visible instead of trusted.

Stop reasons:  final_answer | invalid_output | step_limit | timeout | error
"""

import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

from costs import check_result, confirm_rates, reference_costs  # noqa: E402
from tools import SCHEMAS, CsvSql, PolicyRetriever, calculator, fail  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_DIR = REPO_ROOT / "reports" / "hw07" / "part4" / "snapshots"
DECISIONS = ("Buy Monthly Membership", "Pay Per Ride/Minute")

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"enum": list(DECISIONS)},
        "justification": {"type": "string", "minLength": 40},
        "costs": {"type": "object", "properties": {
            "pay_per_use_total": {"type": "number"}, "membership_fee_total": {"type": "number"},
            "membership_residual_charges": {"type": "number"}, "membership_total": {"type": "number"},
            "months": {"type": "integer"}}, "required": ["pay_per_use_total", "membership_fee_total", "membership_residual_charges", "membership_total", "months"]},
        "break_even": {"type": "object", "properties": {
            "rides_per_month": {"type": "number"}, "actual_rides_per_month": {"type": "number"}}, "required": ["rides_per_month", "actual_rides_per_month"]},
        "weekly": {"type": "array", "items": {"type": "object", "properties": {
            "week": {"type": "string"}, "rides": {"type": "integer"}, "avg_duration_min": {"type": "number"}, "spend": {"type": "number"}},
            "required": ["week", "rides", "avg_duration_min", "spend"]}},
        "citations": {"type": "array", "items": {"type": "object", "properties": {"quote": {"type": "string"}}, "required": ["quote"]}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "justification", "costs", "break_even", "weekly", "citations", "assumptions"],
}

SYSTEM_PROMPT = """You are a bike-share cost analyst for Bay Wheels. Decide whether a rider should buy the MONTHLY membership or PAY PER RIDE/MINUTE, using ONLY tool results.
Never invent a number or a price: every figure you report must come from a tool result. Do arithmetic with SQL or the calculator tool, not in your head.

Work in steps, one tool call at a time:
1. csv_sql, exactly this query (it returns the total ride count, total minutes and the number of calendar months covered, first to last trip inclusive):
   SELECT COUNT(*) AS rides, SUM(duration_min) AS total_minutes, (CAST(strftime('%Y', MAX(started_at)) AS INTEGER) - CAST(strftime('%Y', MIN(started_at)) AS INTEGER)) * 12 + CAST(strftime('%m', MAX(started_at)) AS INTEGER) - CAST(strftime('%m', MIN(started_at)) AS INTEGER) + 1 AS months FROM trips
2. policy_retriever, called TWICE (the two rows are in different passages): once with query "classic bike prices per minute, unlock fee and free minutes" and once with query "ebike prices per minute and unlock fee". You need six numbers: the pay-per-use unlock fee, classic per-minute rate and e-bike per-minute rate; the monthly price; the member classic free minutes and per-minute rate; the member e-bike per-minute rate. The pricing page is a comparison table, so every price row has one value per plan column, and each value is tagged with its column's headline price, e.g. "[column: $29/month]". Pay-per-use is the column tagged $1.00 (single ride); the monthly membership is the column tagged $29/month. Ignore the other columns (day pass, annual plans). A value such as "45 min free, then $0.17/min" means free minutes = 45 and per-minute rate = 0.17; "Free unlocks + $0.17/min" means no unlock fee and rate 0.17.
3. csv_sql, TWO separate queries (copy the shape, put the numbers you found in place of the <...>; in SQLite use the two-argument MAX(a, b), not GREATEST):
   (a) pay-per-use total. Every ride costs the unlock fee plus the per-minute rate x duration_min, with no free minutes, and a different rate for classic_bike and electric_bike:
   SELECT SUM(CASE rideable_type WHEN 'electric_bike' THEN <unlock> + <ebike per-minute> * duration_min ELSE <unlock> + <classic per-minute> * duration_min END) AS pay_per_use_total FROM trips
   (b) membership residual charges, using the MONTHLY MEMBERSHIP column values: classic rides pay the member rate only for the minutes beyond the free minutes; electric rides pay the member rate for all minutes (no unlock fee):
   SELECT SUM(CASE rideable_type WHEN 'electric_bike' THEN <member ebike per-minute> * duration_min ELSE <member classic per-minute> * MAX(0, duration_min - <member classic free minutes>) END) AS membership_residual FROM trips
4. csv_sql: weekly table with strftime('%Y-%W', started_at) AS week, COUNT(*) AS rides, AVG(duration_min) AS avg_duration_min, and SUM of the same pay-per-use CASE expression AS spend, GROUP BY week. If there are more than 8 weeks, return only the 8 weeks with the most rides (ORDER BY rides DESC LIMIT 8) and say so in assumptions.
5. calculator, one call per line, copying the numbers from the earlier tool results (use the rides and months from step 1, never recount them):
   membership fee total:     <monthly price> * <months>
   membership total:         <membership fee total> + <membership residual>
   break-even rides/month:   <monthly price> / (<pay-per-use total> / <rides>)    (<monthly price> is the price of ONE month taken from the policy text, never the membership total)
   actual rides/month:       <rides> / <months>
6. Decide by comparing the two totals: if the membership total is LOWER than the pay-per-use total the decision is "Buy Monthly Membership"; if the pay-per-use total is lower (or equal) the decision is "Pay Per Ride/Minute". Say in the justification which total is lower.

Finish with ONLY one JSON object (no markdown, no text around it) with these keys:
{"decision": "Buy Monthly Membership" only if membership_total < pay_per_use_total, otherwise "Pay Per Ride/Minute",
 "justification": "3-6 sentences with the numbers and which pricing facts you relied on",
 "costs": {"pay_per_use_total": 0.0, "membership_fee_total": 0.0, "membership_residual_charges": 0.0, "membership_total": 0.0, "months": 0},
 "break_even": {"rides_per_month": 0.0, "actual_rides_per_month": 0.0},
 "weekly": [{"week": "2024-23", "rides": 0, "avg_duration_min": 0.0, "spend": 0.0}],
 "citations": [{"quote": "an exact snippet copied from policy_retriever output"}],
 "assumptions": ["each missing or ambiguous thing, e.g. how minutes are billed, which table column you used"]}
If a tool returns success=false, fix the call and retry; if something cannot be known, say so in assumptions."""


def _norm(text: str) -> str:
    """Whitespace/pipe-insensitive form for quote matching; the retriever's '[column: ...]' tags are not page text, so they are ignored."""
    return re.sub(r"[\s|]+", " ", re.sub(r"\s*\[column:[^\]]*\]", "", text)).strip().lower()


def consistency_problem(obj: dict) -> str | None:
    """The answer must agree with itself (no hidden reference needed): the decision follows from its own two totals, and the
    membership total is its own fee plus residual charges."""
    c = obj["costs"]
    if abs(c["membership_fee_total"] + c["membership_residual_charges"] - c["membership_total"]) > 0.05 + 0.001 * abs(c["membership_total"]):
        return (f"costs: membership_total {c['membership_total']} is not membership_fee_total {c['membership_fee_total']} "
                f"+ membership_residual_charges {c['membership_residual_charges']}")
    expected = DECISIONS[0] if c["membership_total"] < c["pay_per_use_total"] else DECISIONS[1]
    if obj["decision"] != expected:
        return (f"decision contradicts your own totals: membership_total {c['membership_total']} vs pay_per_use_total {c['pay_per_use_total']} "
                f"means the decision must be \"{expected}\"")
    return None


def parse_result(text: str) -> tuple[dict | None, str | None]:
    """First JSON object in the model's final text, validated against RESULT_SCHEMA. Returns (result, problem)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        return None, "no JSON object found"
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start: i + 1])
                    jsonschema.validate(obj, RESULT_SCHEMA)
                    problem = consistency_problem(obj)
                    return (None, problem) if problem else (obj, None)
                except (ValueError, jsonschema.ValidationError) as e:
                    if isinstance(e, jsonschema.ValidationError):
                        return None, f"{'.'.join(map(str, e.absolute_path)) or 'top level'}: {e.message}"
                    return None, str(e)
    return None, "unterminated JSON object"


def default_model(thinking: bool = False):
    from langchain_ollama import ChatOllama

    # num_predict and the client timeout stop one runaway generation from blocking the run (the step/time limits only act between model calls)
    return ChatOllama(model="qwen3:8b", temperature=0.0, seed=9871, reasoning=thinking, num_ctx=8192, num_predict=3000,
                      client_kwargs={"timeout": 150})


def run_bike_agent(csv_path, pricing_url, *, run_id=None, snapshot_dir=SNAPSHOT_DIR, model=None, fetcher=None, embedder=None,
                   check_url=True, display_name="uploaded.csv", max_steps=14, timeout_s=300, scenario=None, on_event=None) -> dict:
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langchain_core.tools import StructuredTool
    from langgraph.errors import GraphRecursionError

    run_id = run_id or uuid.uuid4().hex[:10]
    started = time.perf_counter()
    csv_sql = CsvSql(Path(csv_path), display_name)
    kwargs = {"fetcher": fetcher} if fetcher else {}
    retriever = PolicyRetriever(snapshot_dir, run_id, embedder=embedder, check_url=check_url, **kwargs)
    stats = {"calls": 0, "failed": 0, "invalid": 0, "repeated": 0}
    seen_calls: set[str] = set()

    def wrap(name, fn):
        def tool_fn(**kw):
            stats["calls"] += 1
            key = name + json.dumps(kw, sort_keys=True, default=str)
            try:
                jsonschema.validate(kw, SCHEMAS[name])
            except jsonschema.ValidationError as e:
                stats["invalid"] += 1
                out = fail(f"invalid arguments: {e.message}")
            else:
                if key in seen_calls:      # repeat-call guard: an identical call can only return the identical result
                    stats["repeated"] += 1
                    out = fail("you already made this exact call earlier in this run. Do not repeat it: use its earlier result and go on to the next step, "
                               "or reply with the final JSON object.")
                else:
                    seen_calls.add(key)
                    out = fn(**kw)
            stats["failed"] += not out["success"]
            return json.dumps(out, ensure_ascii=False)
        return tool_fn

    tools = [
        StructuredTool.from_function(func=wrap("csv_sql", lambda sql: csv_sql.run(sql)), name="csv_sql", args_schema=SCHEMAS["csv_sql"],
                                     description="Run ONE read-only SQL SELECT over the uploaded trips CSV. " + csv_sql.describe()),
        StructuredTool.from_function(func=wrap("policy_retriever", lambda url, query, k=4: retriever.run(url, query, k)), name="policy_retriever",
                                     args_schema=SCHEMAS["policy_retriever"],
                                     description="Fetch the pricing page and return the k most relevant short snippets (text, source, score)."),
        StructuredTool.from_function(func=wrap("calculator", lambda expression, units=None: calculator(expression, units)), name="calculator",
                                     args_schema=SCHEMAS["calculator"],
                                     description="Safe arithmetic: digits, + - * / ( ) . and spaces only. Returns {value}."),
    ]
    agent = create_agent(model or default_model(), tools, system_prompt=SYSTEM_PROMPT)
    task = (f"Should this rider buy the monthly membership or pay per ride/minute? The trips are in the uploaded CSV ({display_name}; query it "
            f"with csv_sql). The pricing page is {pricing_url}")
    history = [HumanMessage(task)]
    timeline, tokens = [], {"input": 0, "output": 0}

    def emit(event):
        timeline.append(event)
        if on_event:
            on_event(event)

    state = {"steps": 0, "final_text": None, "stop_reason": None, "error": None}

    def now_ms():
        return round((time.perf_counter() - started) * 1000)

    def consume(updates):
        for update in updates:
            if state.get("abandoned"):
                return
            if time.perf_counter() - started > timeout_s:
                state["stop_reason"] = "timeout"
                return
            for node, payload in update.items():
                for m in payload.get("messages", []):
                    history.append(m)
                    if isinstance(m, AIMessage):
                        state["steps"] += 1
                        usage = m.usage_metadata or {}
                        tokens["input"] += usage.get("input_tokens", 0)
                        tokens["output"] += usage.get("output_tokens", 0)
                        if m.tool_calls:
                            for c in m.tool_calls:
                                emit({"step": state["steps"], "kind": "tool_call", "tool": c["name"], "input": c["args"], "t_ms": now_ms()})
                        else:
                            state["final_text"] = m.content if isinstance(m.content, str) else json.dumps(m.content)
                            emit({"step": state["steps"], "kind": "final", "text": state["final_text"][:400], "t_ms": now_ms()})
                    elif isinstance(m, ToolMessage):
                        try:
                            env = json.loads(m.content)
                        except ValueError:
                            env = {"success": False, "error": "unreadable tool output"}
                        emit({"step": state["steps"], "kind": "observation", "tool": m.name, "success": env.get("success"),
                                         "output": (m.content if len(m.content) <= 700 else m.content[:700] + " ..."), "t_ms": now_ms()})

    config = {"recursion_limit": 2 * max_steps + 1}

    def guarded(messages):
        """One agent.stream() pass under a hard wall-clock deadline. A model call that hangs cannot be interrupted from outside, so it is
        abandoned (daemon thread; `abandoned` stops it from touching the result if it ever returns). A model/Ollama failure is reported
        as stop_reason error instead of crashing the page."""
        box = {}

        def target():
            try:
                consume(agent.stream({"messages": list(messages)}, config, stream_mode="updates"))
            except BaseException as e:
                box["exc"] = e

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(max(1.0, timeout_s - (time.perf_counter() - started)))
        if t.is_alive():
            state["abandoned"], state["stop_reason"] = True, "timeout"
        elif isinstance(box.get("exc"), GraphRecursionError):
            state["stop_reason"] = "step_limit"
        elif box.get("exc") is not None:
            state["stop_reason"], state["error"] = "error", f"{type(box['exc']).__name__}: {box['exc']}"

    guarded(history)

    parsed = problem = None
    if state["stop_reason"] is None:
        parsed, problem = parse_result(state["final_text"])
        if parsed is None:                                   # one repair re-prompt
            emit({"step": state["steps"], "kind": "repair", "text": f"final answer rejected: {problem}", "t_ms": now_ms()})
            history.append(HumanMessage(
                f"Your last reply was not valid ({problem}). Reply again with ONLY the JSON object described in your instructions, with every key present "
                f"(costs needs pay_per_use_total, membership_fee_total, membership_residual_charges, membership_total and months as an integer)."))
            state["final_text"] = None
            guarded(history)
            if state["stop_reason"] is None:
                parsed, problem = parse_result(state["final_text"])
        if state["stop_reason"] is None:
            state["stop_reason"] = "final_answer" if parsed else "invalid_output"

    snap = retriever.snapshot
    snap_text = Path(snap["path"]).read_text(encoding="utf-8") if snap else ""
    truth = reference_costs(csv_path)
    citations = []
    for c in (parsed or {}).get("citations", []):
        citations.append({"quote": c["quote"], "found_in_snapshot": bool(c["quote"].strip()) and _norm(c["quote"]) in _norm(snap_text)})
    result = {
        "run_id": run_id, "scenario": scenario, "pricing_url": pricing_url, "csv": display_name,
        "stop_reason": state["stop_reason"], "error": state["error"], "problem": problem if parsed is None else None,
        "steps": state["steps"], "total_time_s": round(time.perf_counter() - started, 2), "tokens": tokens,
        "tool_calls": dict(stats), "timeline": timeline, "result": parsed, "citations": citations, "snapshot": snap,
        "rates_in_snapshot": confirm_rates(snap_text) if snap else None,
        "verification": check_result(parsed, truth), "reference": {k: v for k, v in truth.items() if k != "weeks"},
        "final_text": state["final_text"],
    }
    return result
