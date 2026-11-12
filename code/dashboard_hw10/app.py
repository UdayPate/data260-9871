"""
DATA-260 Homework 10 Part 1 - Streamlit operations dashboard for the semantic-cache + Kafka Planner/Writer/Reviewer system.

    code\\venv\\Scripts\\streamlit.exe run code/dashboard_hw10/app.py --server.port 8873

Pages: Summary (requests, cache hit rate, error rate, latency), Evaluation (Part 2 scores, Part 3 judge validation), Trace lookup (one request, stage by stage).
Everything shown is read from reports/hw10/raw (spans and results written by the real runs); nothing here is typed in.
"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data  # noqa: E402

st.set_page_config(page_title="HW10 operations dashboard", layout="wide")


@st.cache_data(show_spinner=False)
def spans_cached(sig: tuple) -> list[dict]:
    return data.load_spans()


@st.cache_data(show_spinner=False)
def json_cached(sig: tuple, name: str) -> dict:
    return data.load_json(name)


@st.cache_resource(show_spinner=False)
def trace_index(sig: tuple) -> dict[str, list[dict]]:
    """trace_id -> its spans: built once per data change and shared by every session, so a lookup does not rescan the spans."""
    idx: dict[str, list[dict]] = {}
    for s in spans_cached(sig):
        idx.setdefault(s["trace_id"], []).append(s)
    return idx


sig = data.signature()
spans = spans_cached(sig)
page = st.sidebar.radio("Page", ["Summary", "Evaluation", "Trace lookup"])
st.sidebar.caption("Data: reports/hw10/raw (spans_*.jsonl and the Part 2-4 result files).")
st.title("HW10 operations dashboard")


def ms(v) -> str:
    return "n/a" if v is None else f"{v:,.0f} ms"


if page == "Summary":
    st.header("Summary")
    all_rows = data.requests(spans)
    sources = sorted({r["source"] for r in all_rows})
    chosen = st.multiselect("Span files (data source)", sources, default=sources)
    win = st.radio("Time window", ["Everything recorded", "Last 24 h before the newest request"], horizontal=True)
    rows, window = data.in_window(all_rows, chosen, 24 if win.startswith("Last") else None)
    s = data.summary(rows)
    src = f"Source: `request` spans in {', '.join(chosen) or 'none'}. Window: {window}."
    st.caption("These are the traces recorded by the HW10 experiments, not live production traffic. The latency experiment deliberately asked 50 new questions, so the hit rate "
               "below reflects how the experiments were designed.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requests", s["requests"])
    c1.caption(src)
    c2.metric("Semantic-cache hit rate", "n/a" if s["hit_rate_pct"] is None else f"{s['hit_rate_pct']}%", f"{s['hits']} hits / {s['misses']} misses", delta_color="off")
    c2.caption(f"Source: `cache_lookup` spans (path=hit vs path=miss). Window: {window}.")
    c3.metric("Error rate", "n/a" if s["error_rate_pct"] is None else f"{s['error_rate_pct']}%", f"{s['errors']} of {s['requests']} requests", delta_color="off")
    c3.caption(f"Source: `request` spans, status=error (no answer from the pipeline). Window: {window}.")
    c4.metric("End-to-end latency, cache MISS (p50 / p95)", f"{ms(s['miss_p50'])} / {ms(s['miss_p95'])}")
    c4.metric("End-to-end latency, cache HIT (p50 / p95)", f"{ms(s['hit_p50'])} / {ms(s['hit_p95'])}")
    c4.caption(f"Source: `request` span durations, hits and misses kept separate. Window: {window}.")
    if rows:
        df = pd.DataFrame(rows)
        st.subheader("Requests by path")
        st.dataframe(df.groupby(["source", "path", "status"]).agg(requests=("trace_id", "count"), p50_ms=("latency_ms", "median")).round(1).reset_index(), width="stretch")
        errs = df[df["status"] == "error"]
        if len(errs):
            st.subheader("Failed requests")
            st.dataframe(errs[["trace_id", "path", "error", "latency_ms", "source"]], width="stretch")
    try:
        lat = json_cached(sig, "part4_latency_table.json")
        st.subheader("Stage latency, 50 confirmed cache misses (Part 4.3)")
        st.caption("Source: raw/part4_latency_table.json, computed from raw/spans_latency.jsonl. % = stage time / cache-miss end-to-end time.")
        order = ["cache_lookup", "planner", "writer", "reviewer", "queue_wait_total", "evaluation", "e2e"]
        st.dataframe(pd.DataFrame([{"stage": lat["stages"][k]["label"], "p50 (ms)": lat["stages"][k]["p50_ms"], "p95 (ms)": lat["stages"][k]["p95_ms"],
                                    "% of cache-miss end-to-end": lat["stages"][k]["pct_of_e2e"]} for k in order]), width="stretch", hide_index=True)
        st.caption(f"Cache-hit latency (separate metric, {lat['cache_hit']['n']} repeats): p50 {lat['cache_hit']['p50_ms']} ms, p95 {lat['cache_hit']['p95_ms']} ms.")
    except FileNotFoundError:
        st.info("raw/part4_latency_table.json not found: run code/tracing_hw10/run_latency.py and summarize_latency.py.")

elif page == "Evaluation":
    st.header("Evaluation")
    try:
        ev = json_cached(sig, "part2_eval_results.json")
        j3 = json_cached(sig, "part3_judge_scores.json")
    except FileNotFoundError as exc:
        st.error(f"Missing result file: {exc.filename}")
        st.stop()
    st.subheader("Part 2 - pipeline evaluation, scores by stage and case (1-5)")
    j = ev["judge"]
    st.caption(f"Source: raw/part2_eval_results.json, run {ev['run_at']}. Judge: {j['framework']}, {j['model']} (local, Ollama), temperature {j['temperature']}, seed {j['seed']}.")
    rows = []
    for r in ev["records"]:
        if r["status"] != "ok":
            continue
        sc = r["scores"]
        rows.append({"case": r["question_no"], "trace_id": r["trace_id"], "question": r["inputs"]["draft"]["value"]["question"].split("Question: ")[-1],
                     "Plan Quality (Planner)": sc["plan_quality"]["score"], "Writer Helpfulness (Writer)": sc["writer_helpfulness"]["score"],
                     "Final Helpfulness (Reviewer)": sc["final_helpfulness"]["score"], "final - draft": sc["final_vs_draft"]["difference"],
                     "final text = draft": sc["final_vs_draft"]["final_equals_draft"], "Reviewer status": sc["final_vs_draft"]["reviewer_status"]})
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)
    stages = ["Plan Quality (Planner)", "Writer Helpfulness (Writer)", "Final Helpfulness (Reviewer)"]
    means = df[stages].mean().rename("mean score").reset_index().rename(columns={"index": "stage"})
    st.altair_chart(alt.Chart(means).mark_bar().encode(x=alt.X("stage:N", sort=None, title=None), y=alt.Y("mean score:Q", scale=alt.Scale(domain=[0, 5])), tooltip=["stage", "mean score"]), width="stretch")
    same = int(df["final text = draft"].sum())
    st.markdown(f"**Interpretation.** Mean scores: Planner {df[stages[0]].mean():.2f}, Writer {df[stages[1]].mean():.2f}, Reviewer output {df[stages[2]].mean():.2f}. "
                f"The final answer did not improve on the draft (mean difference {df['final - draft'].mean():+.2f}): in {same} of {len(df)} cases the final text is the Writer's draft word for word, "
                "because the Reviewer only approves or rejects. So the pipeline's quality is set by the Writer; the Planner scores lowest, and the Reviewer adds a gate but no improvement. "
                f"With {len(df)} cases these means are indicative only.")
    st.subheader("Part 3 - is the judge reliable? (20 human-labelled drafts)")
    s = j3["statistics"]
    st.caption(f"Source: raw/part3_judge_scores.json, run {j3['run_at']}. Same judge settings, 3 runs on the same 20 drafts. Human labels (1-5) were committed before the judge ran.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Spearman correlation (human vs judge)", s["spearman_rho_run1"], f"p = {s['spearman_p_run1']}", delta_color="off")
    m2.metric("Mean absolute difference", f"{s['mean_abs_difference_run1']} points")
    m3.metric("Cases whose score changed across 3 runs", f"{s['cases_with_any_change_across_runs']} of {s['n_scored']}")
    m4.metric("Mean / max change between runs", f"{s['mean_abs_change']} / {s['max_abs_change']}")
    cdf = pd.DataFrame([{"case": c["case_id"], "human": c["human_label"], "judge run 1": c["judge_scores"][0], "judge run 2": c["judge_scores"][1], "judge run 3": c["judge_scores"][2],
                         "judge - human": c["judge_scores"][0] - c["human_label"]} for c in j3["cases"]])
    left, right = st.columns([3, 2])
    left.dataframe(cdf, width="stretch", hide_index=True)
    right.altair_chart(alt.Chart(cdf).mark_circle(size=120, opacity=0.6).encode(x=alt.X("human:Q", scale=alt.Scale(domain=[0.5, 5.5])), y=alt.Y("judge run 1:Q", scale=alt.Scale(domain=[0.5, 5.5])),
                                                                              tooltip=["case", "human", "judge run 1"]).properties(title="judge vs human (perfect agreement = diagonal)"), width="stretch")
    st.markdown(f"**Interpretation.** The judge is perfectly repeatable ({s['pairwise_changed']} changes in {s['pairwise_comparisons']} run comparisons) but only weakly agrees with the human labels "
                f"(Spearman {s['spearman_rho_run1']}, average miss {s['mean_abs_difference_run1']} points). It rewards answers that invent facts and penalises correct 'not available' answers, "
                "so it should not gate a deployment yet.")

else:
    st.header("Trace lookup")
    idx = trace_index(sig)
    try:
        known = json_cached(sig, "part4_trace_ids.json")
    except FileNotFoundError:
        known = {}
    labels = {"cache_miss_success": "cache MISS (success)", "cache_hit": "cache HIT", "failed": "FAILED"}
    st.caption("Data source: spans_*.jsonl (one span per stage). The three required traces (Part 4.2) are the buttons below; any other trace_id from the span files also works.")
    cols = st.columns(3)
    for col, key in zip(cols, labels, strict=False):
        if key in known and col.button(f"{labels[key]}: {known[key]['trace_id'][:8]}..."):
            st.session_state["trace_id"] = known[key]["trace_id"]
    tid = st.text_input("trace_id", key="trace_id", placeholder="paste a trace_id (the correlation_id of a request)")
    if tid.strip():
        rows = sorted(idx.get(tid.strip(), []), key=lambda s: (s["start_ms"], -s["duration_ms"]))
        if not rows:
            st.warning(f"No spans found for trace_id {tid.strip()!r}.")
        else:
            kind = data.trace_kind(rows)
            (st.error if "FAILED" in kind else st.success if "HIT" in kind else st.info)(f"**{kind}** - {len(rows)} spans, trace_id `{tid.strip()}`")
            t0 = rows[0]["start_ms"]
            tdf = pd.DataFrame([{"#": i, "stage": s["stage"], "start": s["start"][11:], "end": s["end"][11:], "duration (ms)": s["duration_ms"], "status": s["status"], "error": s["error"] or "",
                                 "details": ", ".join(f"{k}={v}" for k, v in s["attrs"].items() if v is not None and k in ("path", "similarity", "pipeline_status", "attempts", "stored", "topic"))}
                                for i, s in enumerate(rows, 1)])
            st.dataframe(tdf, width="stretch", hide_index=True)
            gdf = pd.DataFrame([{"stage": s["stage"], "from (ms)": s["start_ms"] - t0, "to (ms)": s["end_ms"] - t0, "status": s["status"]} for s in rows])
            st.altair_chart(alt.Chart(gdf).mark_bar().encode(y=alt.Y("stage:N", sort=list(gdf["stage"]), title=None), x=alt.X("from (ms):Q", title="ms since the first span"), x2="to (ms):Q",
                                                              color=alt.Color("status:N", scale=alt.Scale(domain=["ok", "error"], range=["#4c78a8", "#e45756"])),
                                                              tooltip=["stage", "from (ms)", "to (ms)", "status"]), width="stretch")
            bad = [s for s in rows if s["status"] == "error" and s["stage"] != "request"]
            if bad:
                st.error("Failing stage: " + ", ".join(f"**{s['stage']}** ({s['error']})" for s in bad))
