"""
Builds reports/hw10/Patel_HW10_report.tex from the repo's real files (copied from reports/hw08/build_report.py; the helpers are unchanged
except that md() also renders *italic*):
  - code listings are cut out of the source files by name with `ast` (src_of) or between two marker lines (between)
  - tables are filled from METRICS.md / the saved JSON (raw/*.json), log excerpts from the saved raw/*.log and *.txt files
  - text comes from METRICS.md and AI_USE.md
Then compile:  cd reports/hw10 && /home/uday/bin/tectonic -X compile Patel_HW10_report.tex
    python3 reports/hw10/build_report.py [--preview]
"""
import ast
import json
import re
import sys
from pathlib import Path

HW = Path(__file__).resolve().parent                 # reports/hwNN
REPO = HW.parent.parent
RAW = HW / "raw"
OUT = HW / "Patel_HW10_report.tex"
# Leave as PLACEHOLDER_HASH until the final commit is tagged; then set the full 40-character hash of the tag (git rev-parse hw10) and rebuild.
PREVIEW = "--preview" in sys.argv  # development only: lets the build run before AI_USE.md is filled in (never use the output)
HASH = "PLACEHOLDER_HASH"

# lstlisting / pdflatex choke on non-ASCII, so every piece of text is folded to ASCII first
ASCII = {"\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2192": "->", "\u2190": "<-", "\u2265": ">=",
         "\u2264": "<=", "\u00d7": "x", "\u00b0": "deg", "\u00a0": " ", "\u2713": "ok", "\u2717": "x", "\u2022": "*", "\ufffd": "'", "\u00e9": "e", "\u2011": "-"}
figs = []


def asc(s):
    s = "".join(ASCII.get(c, c) for c in s)
    return s.encode("ascii", "replace").decode("ascii")


def esc(s):
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(c, c) for c in asc(s))


def md(s):
    """markdown-lite -> LaTeX: `code` (may break at _ and /), **bold**; everything else escaped."""
    out = []
    for i, part in enumerate(re.split(r"(`[^`]*`)", s)):
        if i % 2:
            code = esc(part[1:-1]).replace(r"\_", r"\_\allowbreak{}").replace("/", r"/\allowbreak{}").replace(":", r":\allowbreak{}")
            out.append(r"\texttt{" + code + "}")
        else:
            t = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", esc(part).replace(r"\_", r"\_\allowbreak{}"))
            out.append(re.sub(r"(?<![\w*])\*(?!\*)(.+?)(?<!\*)\*(?!\w)", r"\\emph{\1}", t))
    return "".join(out)


def lst(code, size="scriptsize"):
    code = asc(code).replace("\t", "    ").rstrip("\n")
    return f"\\begingroup\\lstset{{basicstyle=\\ttfamily\\{size}}}\n\\begin{{lstlisting}}\n{code}\n\\end{{lstlisting}}\n\\endgroup\n"


def para(s):
    return md(s) + "\n\n"


def fig(path, caption, h=0.30, w=0.82):
    """The required two-line pattern: \\includegraphics + \\small \\textit{Figure N: caption} (not \\caption). Tall screenshots: raise h, w."""
    figs.append(path)
    return (f"\\begin{{center}}\n\\includegraphics[width={w}\\linewidth,height={h}\\textheight,keepaspectratio]{{screenshots/{path}}}\\\\[2pt]\n"
            f"\\small \\textit{{Figure {len(figs)}: {md(caption)}}}\n\\end{{center}}\n")


def table(headers, rows, spec, size="small"):
    """Text width is about 6.7in; each column also costs 12pt of padding (6pt when size is footnotesize/scriptsize): keep sum(p{} widths) under that."""
    pad = "\\setlength{\\tabcolsep}{3pt}" if size in ("footnotesize", "scriptsize") else ""
    spec = re.sub(r"p\{", r">{\\raggedright\\arraybackslash}p{", spec)
    out = f"\\begin{{center}}\n{{\\{size}{pad}\n\\begin{{tabular}}{{{spec}}}\n\\toprule\n" + " & ".join(f"\\textbf{{{md(h)}}}" for h in headers) + " \\\\\n\\midrule\n"
    for r in rows:
        out += " & ".join(md(str(c)) for c in r) + " \\\\\n"
    return out + "\\bottomrule\n\\end{tabular}}\n\\end{center}\n"


def src_of(relpath, qualname):
    """Exact source text of a function / class / method ('Class.method') / top-level assignment, cut out of the file."""
    text = (REPO / relpath).read_text(encoding="utf-8")
    tree, lines, node = ast.parse(text), text.splitlines(), None
    node = tree
    for part in qualname.split("."):
        node = next(n for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign)) and
                    (getattr(n, "name", None) == part or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == part for t in n.targets))))
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return "\n".join(lines[start - 1: node.end_lineno])


def metrics_section(title):
    text = (HW / "METRICS.md").read_text(encoding="utf-8")
    return re.search(r"^## " + re.escape(title) + r".*?(?=^## |\Z)", text, flags=re.S | re.M).group(0)


def jload(p):
    return json.loads((HW / p).read_text(encoding="utf-8"))


def between(relpath, start, stop):
    """Source lines from the first line starting with `start` up to (not including) the next line starting with `stop`."""
    lines = (REPO / relpath).read_text(encoding="utf-8").splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith(start))
    j = next(k for k in range(i + 1, len(lines)) if lines[k].startswith(stop))
    return "\n".join(lines[i:j])


def rawtext(name):
    return (RAW / name).read_text(encoding="utf-8", errors="replace").replace("\ufeff", "")


def logl(name, keep=None, drop=None, body=True):
    """Timestamped log lines of a raw file, optionally filtered; long `body=...` payloads are shortened to body={...}."""
    out = []
    for ln in rawtext(name).splitlines():
        if not re.match(r"20\d\d-", ln) or (keep and not re.search(keep, ln)) or (drop and re.search(drop, ln)):
            continue
        out.append(re.sub(r" body=.*", " body={...}", ln) if not body else ln)
    return out


def md_table(section, spec, size="footnotesize"):
    """First markdown table of a METRICS.md section as a LaTeX table."""
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in section.splitlines() if ln.startswith("|")]
    return table(rows[0], rows[2:], spec, size)


def md_block(text):
    """Bullets / numbered items / paragraphs of a METRICS.md section (continuation lines are indented) as LaTeX."""
    items, cur = [], None
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith(("#", "|")):
            cur = None
            continue
        m = re.match(r"^(- |\d+\. )(.*)", ln)
        if m:
            cur = [m.group(1).strip() == "-", m.group(2)]
            items.append(cur)
        elif cur and (ln.startswith(" ") or cur[0] == "para"):
            cur[1] += " " + ln.strip()
        else:
            cur = ["para", ln.strip()]
            items.append(cur)
    out, i = "", 0
    while i < len(items):
        if items[i][0] == "para":
            out += para(items[i][1])
            i += 1
            continue
        kind = "itemize" if items[i][0] is True else "enumerate"
        out += f"\\begin{{{kind}}}\\setlength\\itemsep{{2pt}}\n"
        while i < len(items) and items[i][0] == (kind == "itemize"):
            out += "\\item " + md(items[i][1]) + "\n"
            i += 1
        out += f"\\end{{{kind}}}\n"
    return out




def md_table_n(section, spec, size="footnotesize", n=0):
    """n-th markdown table of a section as a LaTeX table."""
    tables, cur = [], []
    for ln in section.splitlines():
        if ln.startswith("|"):
            cur.append([c.strip() for c in ln.strip().strip("|").split("|")])
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    rows = tables[n]
    return table(rows[0], rows[2:], spec, size)


def msub(title):
    """A '### ' subsection of METRICS.md, fences and tables removed from the body by the callers that need it."""
    text = (HW / "METRICS.md").read_text(encoding="utf-8")
    return re.search(r"^### " + re.escape(title) + r".*?(?=^### |^## |\Z)", text, flags=re.S | re.M).group(0)


def nofence(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def body_only(text):
    """Section text without its heading line."""
    return text.split("\n", 1)[1]


def jsonl(path):
    """Records of a JSON list file, one compact line each (same content as the file)."""
    return "[\n" + ",\n".join("  " + json.dumps(r) for r in json.loads(Path(path).read_text(encoding="utf-8"))) + "\n]"


PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[margin=0.9in]{geometry}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{hyperref}
\usepackage{parskip}
\definecolor{codebg}{RGB}{245,245,245}
\lstset{basicstyle=\ttfamily\footnotesize, backgroundcolor=\color{codebg},
  breaklines=true, frame=single, columns=fullflexible, keepspaces=true,
  showstringspaces=false}
% Formatting rule: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt
\makeatletter
\renewcommand\section{\@startsection{section}{1}{\z@}{-3.0ex \@plus -1ex \@minus -.2ex}{1.2ex \@plus.2ex}{\normalfont\fontsize{14}{17}\selectfont\bfseries}}
\renewcommand\subsection{\@startsection{subsection}{2}{\z@}{-2.2ex \@plus -1ex \@minus -.2ex}{0.8ex \@plus.2ex}{\normalfont\fontsize{12}{14.5}\selectfont\bfseries}}
\makeatother
\emergencystretch=3em

\title{DATA-260 Homework 10 -- Report}
\author{Uday Patel}
\date{}
"""


def short(o, n=170):
    """Copy of a JSON-like object with long strings cut to n characters (for listings of saved messages)."""
    if isinstance(o, dict):
        return {k: short(v, n) for k, v in o.items()}
    if isinstance(o, list):
        return [short(v, n) for v in o]
    return o if not isinstance(o, str) or len(o) <= n else o[:n] + "..."


def render(section, specs):
    """A METRICS.md section in its own order: prose -> paragraphs/lists, markdown tables -> LaTeX tables (specs[i] = (column spec, size)), '### ' -> subsection."""
    lines = section.split("\n", 1)[1].splitlines()
    out, buf, tbl, k = "", [], [], 0

    def flush_text():
        nonlocal out, buf
        if buf:
            out += md_block("\n".join(buf))
            buf = []

    def flush_table():
        nonlocal out, tbl, k
        if tbl:
            rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in tbl]
            spec, size = specs[k]
            out += table(rows[0], rows[2:], spec, size)
            tbl, k = [], k + 1

    for ln in lines:
        if ln.startswith("|"):
            flush_text()
            tbl.append(ln)
            continue
        flush_table()
        if ln.startswith("### "):
            flush_text()
            out += f"\\subsection*{{{md(ln[4:].strip())}}}\n"
        else:
            buf.append(ln)
    flush_table()
    flush_text()
    return out


# ------------------------------------------------------------------------------------------------------------------ preamble + Section 0
T = PREAMBLE
T += r"""\begin{document}
\maketitle
\begin{center}GitHub repository: \url{https://github.com/UdayPate/data260-9871}\end{center}

\section*{Section 0 -- Personal Configuration and Domain}
\begin{tabular}{|l|l|}\hline
\textbf{Value} & \textbf{Result} \\\hline
SID4 & 9871 \\\hline
PORT\_BASE & 8871 \\\hline
PREFIX & s9871 \\\hline
SEED & 9871 \\\hline
VERIFY\_SEED & 269871 \\\hline
DOMAIN\_ID & 7 -- Community sports league fixtures \\\hline
\end{tabular}
\vspace{1em}

\textbf{Hardware:} Lenovo Legion Slim 5 16" (Ryzen 5 7640HS, 16GB RAM, RTX 4060 8GB, 512GB SSD). \\
\textbf{Local model used:} qwen3:8b via Ollama for the HW8 Planner/Writer/Reviewer agents and as the \textbf{judge} (DeepEval GEval 4.3.3; temperature 0, seed 9871, thinking off); sentence-transformers/all-MiniLM-L6-v2 for the semantic cache. \\
\textbf{System evaluated:} HW8 Kafka pipeline (Kafka 3.9, KRaft) behind the HW9 Redis Stack semantic cache; dashboard in Streamlit 1.67.0. \\
\textbf{Repository:} \url{https://github.com/UdayPate/data260-9871} \\
\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw10 tag) \\
{\footnotesize\url{https://github.com/UdayPate/data260-9871/tree/PLACEHOLDER_HASH}} \\
\textbf{Collaborator access:} confirmed working for Sbnikitha and supriyaselvanganesan.

"""

# ------------------------------------------------------------------------------------------------------------------ Part 1
P1 = metrics_section("Part 1")
T += "\\section*{Part 1 -- Streamlit Operations Dashboard}\n"
T += para("Reuse: the dashboard is an operations view of the system built in HW8 and HW9; it adds no new application. It reads the span files and result files that the real runs wrote "
          "(`reports/hw10/raw`). `data.py` holds the pure functions (loading, request table, summary numbers, trace lookup) so they can be tested without Streamlit.")
T += render(P1, [("p{1.0in}p{5.2in}", "small")])
T += lst(src_of("code/dashboard_hw10/data.py", "summary"), "tiny")
T += lst(src_of("code/dashboard_hw10/app.py", "spans_cached") + "\n\n" + src_of("code/dashboard_hw10/app.py", "trace_index"), "scriptsize")
ids = jload("raw/part4_trace_ids.json")
T += fig("fig1_summary.png", "Summary page: request count, cache hit rate, error rate and end-to-end latency, each with its data source and time window (all recorded runs).", 0.80, 0.97)
T += fig("fig2_evaluation.png", "Evaluation page: Part 2 scores by stage and case with the interpretation, and the Part 3 judge validation (Spearman, mean absolute difference, repeatability).", 0.80, 0.97)
T += fig(f"fig3_trace_cache_miss_{ids['cache_miss_success']['trace_id'][:8]}.png", f"Trace lookup page, cache MISS (success), trace\\_id {ids['cache_miss_success']['trace_id']}.", 0.62, 0.97)
T += fig(f"fig4_trace_cache_hit_{ids['cache_hit']['trace_id'][:8]}.png", f"Trace lookup page, cache HIT, trace\\_id {ids['cache_hit']['trace_id']}.", 0.40, 0.97)
T += fig(f"fig5_trace_failed_{ids['failed']['trace_id'][:8]}.png", f"Trace lookup page, FAILED request, trace\\_id {ids['failed']['trace_id']}: failing stage writer.", 0.62, 0.97)

# ------------------------------------------------------------------------------------------------------------------ Part 2
P2 = metrics_section("Part 2")
T += "\\section*{Part 2 -- Automated Evaluation of the Kafka Pipeline}\n"
T += "\\subsection*{2.1 Inputs, linkage and the judge}\n"
T += para("`evaluator.collect` reads the plan (`s9871_tasks`), the draft (`s9871_drafts`) and the final answer (`s9871_final`) from Kafka and joins them on `correlation_id`; it keeps each original message "
          "with its topic, partition, offset and timestamp. It stops at a deadline and skips malformed messages, and a request with a missing message is marked `incomplete`. "
          "The judge is DeepEval **GEval** with a local qwen3:8b (`judge.py`): temperature 0, seed 9871, thinking off, JSON-schema replies and a 120 s timeout per call, "
          "so an unavailable judge gives `judge_unavailable` instead of hanging. GEval asks for 0-10 against a five-band rubric; the bands 0-2, 3-4, 5-6, 7-8, 9-10 are read back as 1-5 (1 = very poor, 5 = excellent). "
          "The same scale is used for the human labels in Part 3.")
T += lst(src_of("code/eval_hw10/judge.py", "make_metric") + "\n\n" + src_of("code/eval_hw10/judge.py", "band_to_score") + "\n\n" + between("code/eval_hw10/judge.py", "CRITERIA = {", "def make_metric"), "tiny")
T += lst(src_of("code/eval_hw10/evaluator.py", "collect"), "tiny")
T += "\\subsection*{2.2 The four criteria}\n"
T += para("Plan Quality (score and reason), Writer Helpfulness (score and trace\\_id), Final Answer Helpfulness (score and final answer) and Final-vs-Draft Improvement (both scores, the difference and an interpretation) are computed in `evaluator.evaluate`:")
T += lst(src_of("code/eval_hw10/evaluator.py", "evaluate"), "tiny")
rec = jload("raw/part2_eval_results.json")["records"][0]
T += para("One saved record (first request; the saved file also holds the full messages and every reason, long strings are cut here):")
T += lst(json.dumps(short({"trace_id": rec["trace_id"], "status": rec["status"], "inputs": rec["inputs"], "scores": rec["scores"]}, 120), indent=1), "tiny")
T += render(P2, [("p{0.25in}p{1.5in}p{0.6in}p{0.55in}p{0.7in}p{0.7in}p{0.45in}p{0.5in}p{0.6in}", "scriptsize"), ("p{3.6in}p{1.5in}", "small")])
T += para("Console output of `run_part2.py` and `test_evaluator.py` is in `RUN_LOG.txt`; the evaluation spans (`evaluation`, same trace\\_id) are in `raw/spans_part2.jsonl`.")

# ------------------------------------------------------------------------------------------------------------------ Part 3
P3 = metrics_section("Part 3")
T += "\\section*{Part 3 -- Validating the Judge}\n"
T += "\\subsection*{3.1 Frozen cases and human labels}\n"
T += para("`eval_cases.json` holds 20 real Writer drafts from the league pipeline (8 fixture-fact questions with database facts, including 2 fixture codes that do not exist, 7 general league questions and 5 questions the system has no data for); "
          "`human_labels.csv` holds my own helpfulness label, 1-5, for each draft. Both were committed (commit `a03b38c`) before any judge score existed (the judge scores are in commit `5192512`); the labels were not changed afterwards. "
          "`verify_hw10.py` checks the commit order and that both files are unchanged.")
cases = jload("eval_cases.json")["cases"]
T += lst("\n".join(f"{c['case_id']}: {c['question_plain']}\n    draft: {c['draft'][:150]}{'...' if len(c['draft']) > 150 else ''}" for c in cases[:4]) + "\n    ... (20 cases in eval_cases.json)", "tiny")
T += lst((HW / "human_labels.csv").read_text(encoding="utf-8").strip().replace("\n", " | ").replace("case_", ""), "tiny")
T += "\\subsection*{3.2 and 3.3 Judge vs human, and repeatability}\n"
T += para("The judge ran three times on the same 20 drafts with identical inputs and settings (`run_part3.py`; per-case data for every run in `raw/part3_judge_scores.json` and `.csv`).")
T += lst(src_of("code/eval_hw10/run_part3.py", "statistics"), "tiny")
T += render(P3, [("p{0.55in}p{2.7in}p{0.5in}p{0.55in}p{0.45in}p{0.45in}p{0.6in}", "scriptsize"), ("p{3.4in}p{2.5in}", "small")])

# ------------------------------------------------------------------------------------------------------------------ Part 4
P41, P43 = metrics_section("Part 4.1"), metrics_section("Part 4.3")
T += "\\section*{Part 4 -- Distributed Tracing and Latency Analysis}\n"
T += "\\subsection*{4.1 Trace propagation}\n"
T += para("`trace_id` is the HW8 `correlation_id`: `CachedQA.ask` creates it, `PipelineClient.ask` uses it as the Kafka message key and `correlation_id`, every agent copies it unchanged, and the evaluator reuses it. "
          "No second identifier exists. Every stage appends one structured JSON span to a span file (`tracing.emit`; a no-op unless `HW10_SPANS` is set, so HW8 and HW9 behave as before):")
T += lst(src_of("code/kafka_hw8/tracing.py", "emit"), "tiny")
T += para("Each agent records its queue wait and its own span inside the shared consume-handle-produce loop (`run_stage`), and the ingress records the cache lookup, the inbox publish and the final answer:")
T += lst(between("code/kafka_hw8/agent_common.py", "        t_start = tracing.now_ms()", "        attempt, out, error = 0, None, None") + "        ...\n" +
         between("code/kafka_hw8/agent_common.py", "        if out is not None or error:", "        if out is None and not"), "tiny")
T += lst(between("code/cache_hw9/qa_service.py", "        w_lookup_end = tracing.now_ms()", "        stale = False") + "        ...\n" +
         between("code/cache_hw9/qa_service.py", "        is_hit = bool(", "        if is_hit:"), "tiny")
span = next(json.loads(x) for x in (RAW / "spans_traces.jsonl").read_text(encoding="utf-8").splitlines() if '"stage": "planner"' in x)
T += para("One real span (the Planner of the miss trace below):")
T += lst(json.dumps(span, indent=1), "tiny")
T += "\\subsection*{4.2 The three required traces}\n"
body41 = P41.split("\n", 1)[1]
intro41, rest41 = body41.split("### ", 1)
T += md_block(intro41)
T += render("## x\n### " + rest41, [("p{0.2in}p{1.0in}p{0.85in}p{0.85in}p{0.8in}p{0.45in}p{1.7in}", "scriptsize")] * 3)
T += "\\subsection*{4.3 Stage-latency experiment}\n"
T += para("`run_latency.py`: 50 requests through the real system, one at a time, against an empty semantic cache. Each request counts only if the response said `is_cached=False` **and** its `cache_lookup` span said `path=miss`; "
          "a question the cache happened to answer would have been skipped and replaced from the pool in `latency_questions.py` (none was). The judge then evaluated the 50 requests in a separate pass so it did not share the GPU with the pipeline being timed. "
          "Percentages use the sum of a stage's time over the 50 requests divided by the sum of their end-to-end (`request` span) times.")
T += render(P43, [("p{3.0in}p{0.9in}p{0.9in}p{1.2in}", "small")])
T += para("The saved table is `raw/part4_latency_table.json`; the spans of all 60 requests are in `raw/spans_latency.jsonl` and `verify_hw10.py` recomputes the p50, p95 and percentages from them.")

# ------------------------------------------------------------------------------------------------------------------ verification + AI_USE
T += "\\section*{Self-check (verification.json)}\n"
ver = jload("verification.json")
broken = re.findall(r"^################ (Broken state \d+): (.*?)\n.*?(\d+)/(\d+) checks passed", rawtext("verify_broken_states.txt"), flags=re.S | re.M)
T += para(f"`verify_hw10.py` runs the real system and {ver['total']} objective checks (commit `{ver['commit_hash'][:7]}`, SEED {ver['SEED']}, VERIFY_SEED {ver['VERIFY_SEED']}): {ver['passed']}/{ver['total']} passed. "
          "It was also run (without the live-model check) against four deliberately broken states and failed where it should (`raw/verify_broken_states.txt`): " +
          "; ".join(f"{d} -> {a}/{b}" for _, d, a, b in broken) + ".")
T += table(["Check", "Result"], [[c["check"].replace("Part ", "P").replace(": ", " - ", 1), "PASS" if c["passed"] else "FAIL"] for c in ver["checks"]], "p{5.4in}l", "footnotesize")

ai = (HW / "AI_USE.md").read_text(encoding="utf-8").split("<!-- OPTIONS")[0]
if PREVIEW:
    ai = ai.replace("TODO", "PREVIEW ONLY")
assert "TODO" not in ai, "AI_USE.md still has TODO placeholders"
T += "\\section*{AI\\_USE}\n"
for blk in re.split(r"\n## ", ai)[1:]:
    head, _, body = blk.partition("\n")
    T += f"\\subsection*{{{md(head.strip())}}}\n" + para(body.strip().replace("\n\n", " ").replace("\n", " "))

T += "\\end{document}\n"
if HASH != "PLACEHOLDER_HASH":
    T = T.replace(r"\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw10 tag) \\", r"\textbf{Tagged commit:} " + HASH + r" (tag: hw10) \\")
    T = T.replace("tree/PLACEHOLDER_HASH", "tree/" + HASH)
OUT.write_text(T, encoding="utf-8", newline="\n")
print("wrote", OUT, len(T.splitlines()), "lines;", len(figs), "figures")
