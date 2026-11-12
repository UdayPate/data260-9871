"""HW10 Part 1 checks: runs the real Streamlit app headlessly (streamlit.testing AppTest) and checks what each page renders against the span files, read independently.
    code\\venv\\Scripts\\python.exe code/dashboard_hw10/test_dashboard.py"""
import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1] / "reports" / "hw10" / "raw"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


spans = [json.loads(line) for p in sorted(RAW.glob("spans_*.jsonl")) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
req = [s for s in spans if s["stage"] == "request"]
hits = [s for s in req if s["attrs"]["path"] == "hit"]
errs = [s for s in req if s["status"] == "error"]
ids = json.loads((RAW / "part4_trace_ids.json").read_text(encoding="utf-8"))

at = AppTest.from_file(str(HERE / "app.py"), default_timeout=60).run()
check("Summary page renders without an exception", not at.exception, str(at.exception))
m = {x.label: x for x in at.metric}
check("Requests metric = number of request spans", m["Requests"].value == str(len(req)), f"{m['Requests'].value} vs {len(req)}")
check("Hit rate matches an independent count", m["Semantic-cache hit rate"].value == f"{round(100 * len(hits) / len(req), 1)}%" and m["Semantic-cache hit rate"].delta.startswith(f"{len(hits)} hits"),
      f"{m['Semantic-cache hit rate'].value} {m['Semantic-cache hit rate'].delta}")
check("Error rate matches an independent count", m["Error rate"].value == f"{round(100 * len(errs) / len(req), 1)}%", m["Error rate"].value)
check("Each summary metric states its window and data source", sum("Window:" in c.value and "Source:" in c.value for c in at.caption) >= 4)

at.multiselect[0].set_value(["spans_latency.jsonl"]).run()
n_lat = sum(1 for p in (RAW / "spans_latency.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(p)["stage"] == "request")
check("Choosing one span file narrows the request count", {x.label: x for x in at.metric}["Requests"].value == str(n_lat), f"{n_lat}")

at.sidebar.radio[0].set_value("Evaluation").run()
check("Evaluation page renders", not at.exception, str(at.exception))
mm = {x.label: x.value for x in at.metric}
check("Evaluation page shows Spearman, mean absolute difference and repeatability",
      "Spearman correlation (human vs judge)" in mm and "Mean absolute difference" in mm and "Cases whose score changed across 3 runs" in mm, str(mm))

at.sidebar.radio[0].set_value("Trace lookup").run()
check("Trace lookup page renders", not at.exception, str(at.exception))
for key, expect in (("cache_miss_success", "CACHE MISS"), ("cache_hit", "CACHE HIT"), ("failed", "CACHE MISS - FAILED")):
    at.text_input[0].set_value(ids[key]["trace_id"]).run()
    text = " ".join(x.value for x in at.success) + " ".join(x.value for x in at.info) + " ".join(x.value for x in at.error)
    check(f"{key}: shown as {expect}", expect in text and not at.exception, text[:90])
    n = sum(1 for s in spans if s["trace_id"] == ids[key]["trace_id"])
    check(f"{key}: table has all {n} spans in stage order", len(at.dataframe[0].value) == n and list(at.dataframe[0].value["start"]) == sorted(at.dataframe[0].value["start"]))
check("failed trace names the failing stage and error", any("writer" in x.value and "ConnectError" in x.value for x in at.error))
at.text_input[0].set_value("not-a-real-trace").run()
check("unknown trace_id gives a warning, not a crash", len(at.warning) == 1 and not at.exception)
print(f"\n{'ALL PASSED' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
