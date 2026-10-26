"""
DATA-260 Homework 7 - Part 4: deterministic tests of the three tools, the reference cost model and the agent wrapper.

No Ollama and no network: a scripted fake chat model plays the LLM, a fake fetcher serves a fixed pricing page, and a small
hand-computed trips CSV is used so every number can be checked by hand.

Run from the repo root, inside the venv:   python code/bikeshare/test_bikeshare.py
"""

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import SYSTEM_PROMPT, _norm, parse_result, run_bike_agent  # noqa: E402
from costs import check_result, confirm_rates, reference_costs  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from tools import CsvSql, PolicyRetriever, annotate_columns, calculator, extract_text, make_passages  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"   ({extra})" if extra and not cond else ""))


TMP = Path(tempfile.mkdtemp(prefix="bike_test_"))
HEADER = "ride_id,rideable_type,started_at,ended_at,start_station_name,start_station_id,end_station_name,end_station_id,start_lat,start_lng,end_lat,end_lng,member_casual"


def write_csv(path, rides):
    lines = [HEADER]
    for i, (kind, start, end) in enumerate(rides):
        lines.append(f"R{i},{kind},{start},{end},A,SF-1,B,SF-2,37.7,-122.4,37.8,-122.5,casual")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# hand-computed rides:  classic 10 min -> ppu 2.90 residual 0;  classic 60 min -> ppu 12.40 residual 2.55;  ebike 20 min -> ppu 10.80 residual 3.40
RIDES = [("classic_bike", "2024-01-15 08:00:00.000", "2024-01-15 08:10:00.000"),
         ("classic_bike", "2024-02-01 09:00:00.000", "2024-02-01 10:00:00.000"),
         ("electric_bike", "2024-03-02 18:00:00.000", "2024-03-02 18:20:00.000")]
SMALL = TMP / "small.csv"
write_csv(SMALL, RIDES)

PAGE = """<html><head><title>x</title><script>var a="$99";</script></head><body>
<h1>Plans &amp; Pricing</h1><p>Month pass</p><p>$29/month</p><p>Classic bike prices</p>
<p>$1.00 to unlock, then $0.19/min</p><p>30 min free, then $0.19/min</p><p>45 min free, then $0.17/min</p>
<p>Ebike prices</p><p>$1.00 unlock + $0.49/min</p><p>Free unlocks + $0.49/min</p><p>Free unlocks + $0.17/min</p>
<p>Single rides are great for one-way trips.</p></body></html>"""
URL = "https://example.test/pricing"


def fake_embedder(texts):
    words = ("month", "29", "unlock", "classic", "ebike", "free", "single")
    m = np.array([[t.lower().count(w) for w in words] + [0.01] for t in texts], dtype=float)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


# ------------------------------------------------------------------ csv_sql
print("\n### csv_sql")
db = CsvSql(SMALL)
r = db.run("SELECT COUNT(*) AS n, ROUND(SUM(duration_min), 2) AS minutes FROM trips")
check("a SELECT returns the rows in the documented shape", r["success"] and r["data"] == {"rows": [{"n": 3, "minutes": 90.0}], "row_count": 1, "source": "uploaded.csv"}, str(r))
check("the envelope carries source and ts", r["source"] == "uploaded.csv" and "ts" in r)
check("duration_min is computed from the timestamps (10, 60 and 20 minutes)",
      [x["duration_min"] for x in db.run("SELECT duration_min FROM trips ORDER BY started_at")["data"]["rows"]] == [10.0, 60.0, 20.0])
check("WITH ... SELECT is allowed", db.run("WITH t AS (SELECT duration_min d FROM trips) SELECT MAX(d) m FROM t")["data"]["rows"] == [{"m": 60.0}])
attacks = ["INSERT INTO trips (ride_id) VALUES ('x')", "UPDATE trips SET ride_id='x'", "DELETE FROM trips", "DROP TABLE trips",
           "CREATE TABLE t2 (a)", "ATTACH DATABASE 'evil.db' AS e", "PRAGMA writable_schema=1", "SELECT 1; DROP TABLE trips",
           "WITH x AS (SELECT 1) INSERT INTO trips (ride_id) SELECT 'y' FROM x", "ALTER TABLE trips ADD COLUMN z", "VACUUM", "REPLACE INTO trips (ride_id) VALUES ('q')"]
rejected = [a for a in attacks if not db.run(a)["success"]]
check(f"all {len(attacks)} write/DDL/multi-statement attempts are rejected", rejected == attacks, str([a for a in attacks if a not in rejected]))
check("and the table is unchanged afterwards", db.run("SELECT COUNT(*) n FROM trips")["data"]["rows"] == [{"n": 3}])
check("a write hidden inside a SELECT-looking statement is denied by the SQLite authorizer, not just by the prefix check",
      not db.run("SELECT 1 FROM trips WHERE 1=(SELECT 1); DELETE FROM trips")["success"])
t0 = time.time()
runaway = db.run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT COUNT(*) FROM c")
check("a runaway recursive query is aborted instead of hanging", (not runaway["success"]) and time.time() - t0 < 60, f"{runaway} {time.time() - t0:.1f}s")
check("bad SQL gives success=false with a readable error", not db.run("SELECT nope FROM trips")["success"] and "SQL error" in db.run("SELECT nope FROM trips")["error"])
check("an empty query is an error", not db.run("  ;  ")["success"])
BIG = TMP / "big.csv"
write_csv(BIG, [("classic_bike", f"2024-01-{1 + i % 28:02d} 08:00:00.000", f"2024-01-{1 + i % 28:02d} 08:05:00.000") for i in range(300)])
big = CsvSql(BIG).run("SELECT * FROM trips")
check("a 300-row result is cut at 200 rows with a truncated note", big["success"] and big["data"]["row_count"] == 200 and "truncated" in big["data"])
BAD = TMP / "bad.csv"
BAD.write_text(HEADER + "\nR1,classic_bike,,,A,1,B,2,0,0,0,0,casual\nR2,classic_bike,2024-01-01 08:00:00,2024-01-01 08:10:00,A,1,B,2,0,0,0,0,casual\n", encoding="utf-8")
bad = CsvSql(BAD)
check("rows with missing timestamps get a NULL duration and are counted", bad.null_duration == 1 and bad.row_count == 2)

# ------------------------------------------------------------------ calculator
print("\n### calculator")
check("arithmetic with precedence and parentheses", calculator("2 + 3 * (4 - 1) / 2")["data"]["value"] == 6.5)
check("units are echoed back", calculator("29 * 12", "USD")["data"] == {"value": 348.0, "units": "USD"})
check("decimals and unary minus", abs(calculator("-1.5 + 0.19 * 10")["data"]["value"] - 0.4) < 1e-9)
for bad_expr in ["__import__('os').system('x')", "2 ** 10", "abs(-1)", "1; 2", "1e5", "a + 1", "", "2 // 3", "5 % 2"]:
    check(f"rejected: {bad_expr!r}", not calculator(bad_expr)["success"])
check("division by zero is an error, not a crash", calculator("1/0")["error"] == "division by zero")
check("a very long expression is refused", not calculator("1+" * 150 + "1")["success"])
deep = calculator("(" * 500 + "1" + ")" * 500)
check("a 500-level nested expression returns an error envelope instead of crashing the tool", deep["success"] is False and "error" in deep, str(deep)[:120])

# ------------------------------------------------------------------ policy_retriever
print("\n### policy_retriever")
fetches = []


def fake_fetch(url):
    fetches.append(url)
    return PAGE


text_lines = extract_text(PAGE)
check("extract_text drops scripts, decodes entities and keeps visible text in order",
      text_lines[0] == "Plans & Pricing" and "$99" not in " ".join(text_lines) and "$29/month" in text_lines)
rep = text_lines * 3
passages = make_passages(rep)
check("make_passages drops duplicate windows: all passages are distinct and fewer than the raw windows",
      len(set(passages)) == len(passages) and len(passages) < len(range(0, len(rep) - 1, 2)), f"{len(passages)} vs {len(range(0, len(rep) - 1, 2))}")
pr = PolicyRetriever(TMP / "snaps", "run1", fetcher=fake_fetch, embedder=fake_embedder, check_url=False)
out = pr.run(URL, "monthly membership price", 3)
check("returns passages with text, source and score", out["success"] and len(out["data"]["passages"]) == 3
      and all(set(p) == {"text", "source", "score"} for p in out["data"]["passages"]), str(out)[:200])
check("the best passage for 'month price' mentions the month pass", "$29/month" in out["data"]["passages"][0]["text"], out["data"]["passages"][0]["text"])
snap_file = TMP / "snaps" / "run1_pricing.txt"
check("the exact text snapshot was saved and its SHA-256 matches", snap_file.exists()
      and pr.snapshot["sha256"] == hashlib.sha256(snap_file.read_bytes()).hexdigest())
meta = json.loads((TMP / "snaps" / "run1_pricing.meta.json").read_text(encoding="utf-8"))
check("the metadata file records url, access time and hash", meta["url"] == URL and meta["accessed_at"] and meta["sha256"] == pr.snapshot["sha256"])
pr.run(URL, "unlock fee")
check("the page is fetched once per run (later calls use the frozen snapshot)", fetches == [URL])
other = pr.run("https://other.test/x", "price")
check("a different URL in the same run is refused", not other["success"] and "bound to" in other["error"])
check("empty query is an error", not pr.run(URL, "  ")["success"])
check("k is capped at 8 and floored at 1", len(pr.run(URL, "price", 50)["data"]["passages"]) <= 8 and len(pr.run(URL, "price", 0)["data"]["passages"]) == 1)
strict = PolicyRetriever(TMP / "snaps", "run2", fetcher=fake_fetch, embedder=fake_embedder)
check("http:// is refused", not strict.run("http://example.test/p", "price")["success"])
check("localhost / private addresses are refused (no SSRF into the local machine)", not strict.run("https://localhost/p", "price")["success"]
      and not strict.run("https://127.0.0.1/p", "price")["success"] and not strict.run("https://192.168.1.1/p", "price")["success"])
check("a fetch failure is reported as success=false", not PolicyRetriever(TMP / "snaps", "run3", fetcher=lambda u: (_ for _ in ()).throw(OSError("boom")),
                                                                          embedder=fake_embedder, check_url=False).run(URL, "price")["success"])
check("rates are confirmed against the snapshot text", confirm_rates(snap_file.read_text(encoding="utf-8"))["all_confirmed"])
check("a snapshot without the rates is NOT confirmed", not confirm_rates("nothing here")["all_confirmed"])

# ------------------------------------------------------------------ reference costs
print("\n### reference cost model (hand-computed)")
ref = reference_costs(SMALL)
check("pay-per-use total = 2.90 + 12.40 + 10.80 = 26.10", ref["pay_per_use_total"] == 26.10, str(ref["pay_per_use_total"]))
check("membership residual = 0 + 2.55 + 3.40 = 5.95", ref["membership_residual"] == 5.95, str(ref["membership_residual"]))
check("Jan 15 to Mar 2 spans 3 calendar months, fee 87.00, membership total 92.95", ref["months"] == 3 and ref["membership_fee_total"] == 87.0 and ref["membership_total"] == 92.95)
check("so pay-per-use wins for three short rides", ref["decision"] == "Pay Per Ride/Minute")
LONG = TMP / "long.csv"
write_csv(LONG, [("electric_bike", f"2024-06-{1 + i % 28:02d} 08:00:00.000", f"2024-06-{1 + i % 28:02d} 08:40:00.000") for i in range(30)])
check("thirty 40-minute e-bike rides in one month: membership wins", reference_costs(LONG)["decision"] == "Buy Monthly Membership")
check("weekly rows add up to the ride count", sum(w["rides"] for w in reference_costs(LONG)["weeks"]) == 30)
check("break-even = 29 / (26.10 / 3 rides) = 3.33 rides per month", ref["break_even_rides_per_month"] == 3.33, str(ref["break_even_rides_per_month"]))
good = {"decision": ref["decision"], "costs": {"pay_per_use_total": 26.1, "membership_total": 92.95, "months": 3}, "break_even": {"rides_per_month": 3.33}}
check("check_result accepts the right numbers", check_result(good, ref)["all_ok"])
check("check_result flags a wrong decision", not check_result({**good, "decision": "Buy Monthly Membership"}, ref)["checks"]["decision"])
check("check_result flags a wrong total", not check_result({**good, "costs": {**good["costs"], "pay_per_use_total": 40}}, ref)["checks"]["pay_per_use_total"])
check("check_result flags a wrong break-even", not check_result({**good, "break_even": {"rides_per_month": 9.9}}, ref)["checks"]["break_even_rides_per_month"])
check("check_result with no result is not ok", not check_result(None, ref)["all_ok"])

# ------------------------------------------------------------------ result parsing
print("\n### final-answer parsing")
VALID = {"decision": "Pay Per Ride/Minute", "justification": "Three short rides cost $26.10 against $92.95 for three months of membership.",
         "costs": {"pay_per_use_total": 26.1, "membership_fee_total": 87.0, "membership_residual_charges": 5.95, "membership_total": 92.95, "months": 3},
         "break_even": {"rides_per_month": 3.33, "actual_rides_per_month": 1.0}, "weekly": [{"week": "2024-02", "rides": 1, "avg_duration_min": 10.0, "spend": 2.9}],
         "citations": [{"quote": "$29/month"}], "assumptions": ["minutes are billed fractionally"]}
check("plain JSON parses", parse_result(json.dumps(VALID))[0] == VALID)
check("JSON inside a markdown fence with prose before it parses", parse_result("Here you go:\n```json\n" + json.dumps(VALID) + "\n```")[0] == VALID)
check("a decision outside the two allowed strings is rejected", parse_result(json.dumps({**VALID, "decision": "Maybe"}))[0] is None)
check("a missing key is rejected", parse_result(json.dumps({k: v for k, v in VALID.items() if k != "costs"}))[0] is None)
no_months = {**VALID, "costs": {k: v for k, v in VALID["costs"].items() if k != "months"}}
check("a nested missing key is rejected and the message names where (costs: 'months' ...)",
      parse_result(json.dumps(no_months))[1] == "costs: 'months' is a required property", str(parse_result(json.dumps(no_months))[1]))
check("text with no JSON is rejected", parse_result("I think you should pay per ride.")[0] is None)
contradict = {**VALID, "decision": "Buy Monthly Membership"}      # its own totals say membership costs 92.95 vs 26.10 pay-per-use
res_c, prob_c = parse_result(json.dumps(contradict))
check("a decision that contradicts the answer's own totals is rejected, and the message says what it should be",
      res_c is None and "must be \"Pay Per Ride/Minute\"" in prob_c, str(prob_c))
res_t, prob_t = parse_result(json.dumps({**VALID, "costs": {**VALID["costs"], "membership_total": 50.0}}))
check("a membership_total that is not fee + residual is rejected", res_t is None and "is not membership_fee_total" in prob_t, str(prob_t))
check("a tie goes to pay-per-use (the rule says: membership only if strictly lower)",
      parse_result(json.dumps({**VALID, "costs": {**VALID["costs"], "pay_per_use_total": 92.95}}))[0] is not None)
check("braces inside a string do not confuse the parser", parse_result(json.dumps({**VALID, "justification": VALID["justification"] + " {not json}"}))[0] is not None)


# ------------------------------------------------------------------ the agent wrapper with a scripted model
print("\n### agent wrapper (scripted fake model)")


class Scripted(BaseChatModel):
    script: list
    calls: int = 0
    seen: list = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(len(messages))
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        if "sleep" in item:
            time.sleep(item["sleep"])
        msg = AIMessage(content=item.get("content", ""), tool_calls=item.get("tool_calls", []),
                        usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})
        return ChatResult(generations=[ChatGeneration(message=msg)])


def call(name, args, i):
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": f"c{i}", "type": "tool_call"}]}


HAPPY = [call("csv_sql", {"sql": "SELECT COUNT(*) n FROM trips"}, 1),
         call("policy_retriever", {"url": URL, "query": "month pass price"}, 2),
         call("calculator", {"expression": "29 * 3"}, 3),
         {"content": json.dumps({**VALID, "citations": [{"quote": "$29/month"}, {"quote": "Unlimited free rides forever"}]})}]


def run(script, **kw):
    model = Scripted(script=script, seen=[])
    out = run_bike_agent(SMALL, URL, model=model, fetcher=fake_fetch, embedder=fake_embedder, check_url=False, snapshot_dir=TMP / "agent_snaps", **kw)
    return out, model


out, model = run(HAPPY, run_id="happy")
kinds = [(e["kind"], e.get("tool")) for e in out["timeline"]]
check("happy path: stop_reason final_answer in 4 steps", out["stop_reason"] == "final_answer" and out["steps"] == 4, f"{out['stop_reason']} {out['steps']}")
check("the timeline shows each tool call followed by its observation, then the final answer",
      kinds == [("tool_call", "csv_sql"), ("observation", "csv_sql"), ("tool_call", "policy_retriever"), ("observation", "policy_retriever"),
                ("tool_call", "calculator"), ("observation", "calculator"), ("final", None)], str(kinds))
check("tool call counts and token totals are tracked", out["tool_calls"]["calls"] == 3 and out["tokens"] == {"input": 400, "output": 40})
check("the snapshot (url, time, sha256) is attached to the result", out["snapshot"]["sha256"] and out["snapshot"]["url"] == URL and out["snapshot"]["accessed_at"])
check("a real quote is marked found_in_snapshot, an invented quote is marked NOT found",
      [c["found_in_snapshot"] for c in out["citations"]] == [True, False], str(out["citations"]))
check("independent verification compares the agent's numbers with the reference", out["verification"]["checked"] and out["verification"]["all_ok"], str(out["verification"]))
check("the evidence rates are confirmed in the snapshot", out["rates_in_snapshot"]["all_confirmed"])
wrong = dict(VALID, decision="Buy Monthly Membership", costs={**VALID["costs"], "pay_per_use_total": 500.0})
out_w, _ = run([{"content": json.dumps(wrong)}])
check("a confidently wrong answer is flagged by verification (decision and total)",
      out_w["stop_reason"] == "final_answer" and not out_w["verification"]["all_ok"] and not out_w["verification"]["checks"]["decision"]
      and not out_w["verification"]["checks"]["pay_per_use_total"])
out_r, model_r = run([{"content": "Sure! Pay per ride."}, {"content": json.dumps(VALID)}])
check("a non-JSON final answer gets exactly one repair re-prompt and then succeeds", out_r["stop_reason"] == "final_answer"
      and any(e["kind"] == "repair" for e in out_r["timeline"]) and model_r.calls == 2)
out_c, model_c = run([{"content": json.dumps(contradict)}, {"content": json.dumps(VALID)}])
check("a self-contradictory answer is sent back once and the corrected answer is accepted",
      out_c["stop_reason"] == "final_answer" and out_c["result"]["decision"] == "Pay Per Ride/Minute" and model_c.calls == 2
      and any("contradicts" in e.get("text", "") for e in out_c["timeline"] if e["kind"] == "repair"))
out_i, model_i = run([{"content": "no json"}, {"content": "still no json"}])
check("two bad answers in a row -> stop_reason invalid_output, no result, no crash", out_i["stop_reason"] == "invalid_output" and out_i["result"] is None and model_i.calls == 2)
out_s, _ = run([call("calculator", {"expression": "1+1"}, 1)] * 50, max_steps=3)
check("a model that never stops is cut off: stop_reason step_limit", out_s["stop_reason"] == "step_limit" and out_s["steps"] <= 4, f"{out_s['stop_reason']} {out_s['steps']}")
same = call("calculator", {"expression": "29 * 3"}, 1)
out_d, _ = run([same, call("calculator", {"expression": "29 * 3"}, 2), call("calculator", {"expression": "29 * 3"}, 3), {"content": json.dumps(VALID)}])
obs_d = [e for e in out_d["timeline"] if e["kind"] == "observation"]
check("an identical tool call repeated in one run is refused (first runs, the next two are told not to repeat) and the run still finishes",
      [e["success"] for e in obs_d] == [True, False, False] and "already made this exact call" in obs_d[1]["output"]
      and out_d["tool_calls"]["repeated"] == 2 and out_d["stop_reason"] == "final_answer", str([e["success"] for e in obs_d]))
out_d2, _ = run([call("calculator", {"expression": "29 * 3"}, 1), call("calculator", {"expression": "29 * 4"}, 2), {"content": json.dumps(VALID)}])
check("different arguments are NOT treated as a repeat", out_d2["tool_calls"]["repeated"] == 0 and all(e["success"] for e in out_d2["timeline"] if e["kind"] == "observation"))
t0 = time.time()
out_h, _ = run([{"sleep": 25, "content": "never arrives"}], timeout_s=2)
check("a model call that hangs is abandoned at the deadline: stop_reason timeout, returned in seconds, not after the call",
      out_h["stop_reason"] == "timeout" and time.time() - t0 < 12 and out_h["result"] is None, f"{out_h['stop_reason']} {time.time() - t0:.1f}s")
check("a timed-out run still reports its snapshot-less state and a verification (not checked) instead of crashing", out_h["verification"]["checked"] is False)
out_e, _ = run([RuntimeError("ollama is down")])
check("a model failure is reported as stop_reason error with the message, not raised", out_e["stop_reason"] == "error" and "ollama is down" in out_e["error"])
out_b, _ = run([call("csv_sql", {}, 1), call("calculator", {"expression": "1 +"}, 2), {"content": json.dumps(VALID)}])
obs = [e for e in out_b["timeline"] if e["kind"] == "observation"]
check("invalid arguments and a bad expression come back as success=false observations and the run continues",
      [e["success"] for e in obs] == [False, False] and out_b["stop_reason"] == "final_answer" and out_b["tool_calls"]["failed"] == 2 and out_b["tool_calls"]["invalid"] == 1)
out_t, _ = run([{"content": "", "tool_calls": [{"name": "csv_sql", "args": {"sql": "DROP TABLE trips"}, "id": "d1", "type": "tool_call"}]},
                call("csv_sql", {"sql": "SELECT COUNT(*) n FROM trips"}, 2), {"content": json.dumps(VALID)}])
obs = [e for e in out_t["timeline"] if e["kind"] == "observation"]
check("a DROP TABLE attempt by the model is refused and the data is intact afterwards",
      '"success": false' in obs[0]["output"] and '"n": 3' in obs[1]["output"], obs[0]["output"][:120])
check("the system prompt tells the model to pick the pricing column by its tag ($1.00 pay-per-use, $29/month membership)",
      "[column: $29/month]" in SYSTEM_PROMPT and "tagged $1.00" in SYSTEM_PROMPT)

# ------------------------------------------------------------------ column tagging of flattened comparison tables
print("\n### column tagging")
TABLE = ["Single ride", "Day pass", "Month pass", "$1.00", "$15/day", "$29/month", "Get the app",
         "Classic bike prices", "$1.00 to unlock, then $0.19/min", "30 min free, then $0.19/min", "45 min free, then $0.17/min",
         "Ebike prices", "$1.00 unlock + $0.49/min", "Free unlocks + $0.49/min", "Free unlocks + $0.17/min"]
tagged = annotate_columns(TABLE)
check("each classic-row value is tagged with its column's headline price",
      tagged[8:11] == ["$1.00 to unlock, then $0.19/min [column: $1.00]", "30 min free, then $0.19/min [column: $15/day]",
                       "45 min free, then $0.17/min [column: $29/month]"], str(tagged[8:11]))
check("the ebike row is tagged the same way", tagged[12:15] == ["$1.00 unlock + $0.49/min [column: $1.00]", "Free unlocks + $0.49/min [column: $15/day]",
                                                               "Free unlocks + $0.17/min [column: $29/month]"])
check("lines that are not price-row values are left alone", tagged[:8] == TABLE[:8] and tagged[11] == TABLE[11])
check("a page with no headline price run is returned unchanged", annotate_columns(["Classic bike prices", "a $1", "b free", "c free"]) == ["Classic bike prices", "a $1", "b free", "c free"])
check("a price row with the wrong number of values is not tagged", annotate_columns(TABLE[:3] + TABLE[3:6] + ["Classic bike prices", "a $1", "b free"])[6:] ==["Classic bike prices", "a $1", "b free"])
TABLE_PAGE = "<html><body>" + "".join(f"<p>{x}</p>" for x in TABLE) + "</body></html>"
pt = PolicyRetriever(TMP / "snaps", "run_tag", fetcher=lambda u: TABLE_PAGE, embedder=fake_embedder, check_url=False)
got = pt.run(URL, "month pass 45 min free", 8)["data"]["passages"]
check("passages returned to the model carry the column tags", any("45 min free, then $0.17/min [column: $29/month]" in p["text"] for p in got), str([p["text"] for p in got][:2]))
check("but the saved snapshot is the exact page text with no tags", "[column:" not in (TMP / "snaps" / "run_tag_pricing.txt").read_text(encoding="utf-8"))
quote = next(p["text"] for p in got if "[column: $29/month]" in p["text"])
check("a quote copied from a tagged passage still matches the snapshot (tags ignored), an altered quote does not",
      _norm(quote) in _norm((TMP / "snaps" / "run_tag_pricing.txt").read_text(encoding="utf-8")) and _norm(quote + " 99") not in _norm("\n".join(TABLE)))

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
for n in failed:
    print("FAILED:", n)
sys.exit(1 if failed else 0)
