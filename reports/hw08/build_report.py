"""
Builds reports/hw08/Patel_HW08_report.tex from the repo's real files (copied from reports/hw07/build_report.py; the helpers are unchanged
except that md() also renders *italic*):
  - code listings are cut out of the source files by name with `ast` (src_of) or between two marker lines (between)
  - tables are filled from METRICS.md / the saved JSON (raw/*.json), log excerpts from the saved raw/*.log and *.txt files
  - text comes from METRICS.md and AI_USE.md
Then compile:  cd reports/hw08 && /home/uday/bin/tectonic -X compile Patel_HW08_report.tex
    python3 reports/hw08/build_report.py
"""
import ast
import json
import re
import sys
from pathlib import Path

HW = Path(__file__).resolve().parent                 # reports/hwNN
REPO = HW.parent.parent
RAW = HW / "raw"
OUT = HW / "Patel_HW08_report.tex"
# Leave as PLACEHOLDER_HASH until the final commit is tagged; then set the full 40-character hash of the tag (git rev-parse hwN) and rebuild.
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
            code = esc(part[1:-1]).replace(r"\_", r"\_\allowbreak{}").replace("/", r"/\allowbreak{}")
            out.append(r"\texttt{" + code + "}")
        else:
            t = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", esc(part))
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


# ------------------------------------------------------------------------------------------------------------------ preamble + Section 0
T = r"""\documentclass[11pt]{article}
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

\title{DATA-260 Homework 8 -- Report}
\author{Uday Patel}
\date{}

\begin{document}
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
\textbf{Local model used:} qwen3:8b via Ollama (thinking off, sampling seed 9871) in Part 2 only. Part 1 uses no model. The Part 3 failure tests run the Writer in a model-free stub mode (disclosed in Part 3). \\
\textbf{Kafka:} official apache/kafka:3.9.0 image, single node (KRaft), docker compose; Python client confluent-kafka 2.16.1; FastAPI on port 8871. \\
\textbf{Repository:} \url{https://github.com/UdayPate/data260-9871} \\
\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw8 tag) \\
{\footnotesize\url{https://github.com/UdayPate/data260-9871/tree/PLACEHOLDER_HASH}} \\
\textbf{Collaborator access:} confirmed working for Sbnikitha and supriyaselvanganesan.

"""

# ------------------------------------------------------------------------------------------------------------------ Part 1
demo = rawtext("part1_demo_output.txt")


def body_of(prefix):
    """The JSON payload of the first demo log line containing `prefix` ('SENT request' / 'RECEIVED response'), pretty-printed."""
    ln = next(ln for ln in demo.splitlines() if prefix in ln and "body=" in ln)
    return json.dumps(json.loads(ln.split("body=", 1)[1]), indent=2)


T += "\\section*{Part 1 -- Backend Service Request/Response over Kafka}\n"
T += para("The Fixture service (domain 7) is split into a client side (FastAPI wrapper `api.py`, the demo `homework_demo.py`, both using `kafka_rpc.KafkaRpcClient`) and a worker (`worker.py`) that talk only through two Kafka topics. "
          "The worker keeps the fixtures in a plain Python dict and generates `entity_id` with `uuid4`. Kafka client: **confluent-kafka** (Confluent's own, actively released librdkafka client with Windows and Linux wheels, manual offset commits and partition control).")
T += "\\subsection*{Topics and docker compose}\n"
T += table(["Topic", "Written by", "Read by", "Partitions"], [["`s9871_entity_requests`", "client / FastAPI", "worker", "1"], ["`s9871_entity_responses`", "worker", "client / FastAPI", "1"]], "llll")
T += para("`docker compose up` starts the official `apache/kafka:3.9.0` image in single-node mode, a one-shot `kafka-init` job that creates the topics, the worker and the FastAPI service. Excerpt (broker service):")
T += "\\begin{samepage}\n" + lst(between("docker-compose.yml", "  kafka:", "  # One-shot"), "tiny") + "\\end{samepage}\n"
T += "\\subsection*{Message schemas}\n"
T += para("Request (every request carries `correlation_id`, `reply_to`, `operation` and `data`) -- real message from `homework_demo.py`:")
T += lst(body_of("SENT request"), "scriptsize")
T += para("Success response to CREATE_ENTITY (echoes the correlation_id, adds the generated `entity_id`):")
T += lst(body_of("RECEIVED response"), "scriptsize")
get_req = next(ln for ln in demo.splitlines() if "SENT request" in ln and "GET_ENTITY" in ln)
get_resp = next(ln for ln in demo.splitlines() if "RECEIVED response" in ln and '"entity"' in ln)
T += para("GET_ENTITY request and its success response:")
T += lst(json.dumps(json.loads(get_req.split("body=", 1)[1]), indent=2) + "\n" + json.dumps(json.loads(get_resp.split("body=", 1)[1]), indent=2), "scriptsize")
errs = [ln for ln in rawtext("part1_http_tests.txt").splitlines() if ln.startswith("--- ") or ln.startswith('{"correlation_id"')]
T += para("Error responses (real output of API calls; every error carries the original correlation_id, and a caller-supplied `X-Correlation-ID` comes back unchanged, see `my-fixed-id-1`):")
T += lst("\n".join(errs[errs.index("--- get unknown"):] if "--- get unknown" in errs else errs), "tiny")
T += "\\subsection*{Complete correlation\\_id flow (CREATE\\_ENTITY in the demo log)}\n"
cl = {k: re.search(r"corr=([0-9a-f-]{36})", next(ln for ln in demo.splitlines() if pat in ln)).group(1) for k, pat in (
    ("client creates and sends", "[client] SENT request"), ("worker receives", "[worker] RECEIVED"), ("worker processes", "[worker] PROCESSED"),
    ("worker replies", "[worker] REPLIED"), ("client receives the response", "[client] RECEIVED response"))}
assert len(set(cl.values())) == 1, "correlation_id changed along the flow"
T += table(["Hop", "Where", "correlation_id"], [[str(i), k, f"`{v}`"] for i, (k, v) in enumerate(cl.items(), 1)], "rlp{3.4in}", "footnotesize")
T += para("The same 36-character value appears at all five hops (checked by the script that builds this report); the response is matched to the waiting caller only by this value.")
T += "\\subsection*{Validation, processing and reply code}\n"
T += lst(src_of("code/kafka_hw8/common.py", "validate_fixture") + "\n\n" + src_of("code/kafka_hw8/worker.py", "handle_request"), "tiny")
T += lst(between("code/kafka_hw8/worker.py", "        response = handle_request(request)", "    consumer.close()"), "tiny")
T += lst(src_of("code/kafka_hw8/kafka_rpc.py", "KafkaRpcClient.request") + "\n\n" + src_of("code/kafka_hw8/api.py", "call"), "tiny")
T += "\\subsection*{Required evidence}\n"
T += para("**1. Docker containers running** -- `docker ps` shows the Kafka, worker and FastAPI containers; the worker log shows \"Consumer is ready and listening...\" and the FastAPI log shows the server started at http://127.0.0.1:8871.")
T += fig("part1_docker_ps.png", "`docker ps`: `s9871-kafka` (healthy), `s9871-worker` and `s9871-api` (port 8871) running.", h=0.17, w=0.95)
T += fig("part1_worker_log.png", "`docker logs s9871-worker`: \"Consumer is ready and listening...\", then RECEIVED / PROCESSED / REPLIED for every request.", h=0.45, w=0.95)
T += fig("part1_api_log.png", "`docker logs s9871-api`: \"FastAPI server started at http://127.0.0.1:8871\" and the HTTP -> Kafka -> HTTP flow of a CREATE_ENTITY call.", h=0.28, w=0.95)
T += para("**2. CREATE_ENTITY and GET_ENTITY execution** and **3. message-flow logs** -- `homework_demo.py` (the Kafka client): the request sent to `s9871_entity_requests`, the worker's receive / process / reply lines, and the response received by the client, for both operations. "
          "(These two screenshots are a later run of the same script, so the offsets are 10 and 11; the text excerpt below is the first run.)")
T += fig("part1_demo_output_top.png", "`homework_demo.py`, steps 1-6: one correlation_id, CREATE_ENTITY sent, worker receives / processes / replies, client receives the response with the generated entity_id.", h=0.40, w=0.95)
T += fig("part1_demo_output_bottom.png", "`homework_demo.py`, steps 7-10: entity_id extracted, GET_ENTITY full sequence, the retrieved entity and the correlation_id checks.", h=0.55, w=0.95)
T += fig("part1_api_wrapper.png", "FastAPI wrapper (`docker logs s9871-api`): error requests (unknown field, `agree_terms`, unknown operation) go HTTP -> Kafka -> HTTP with the correlation_id unchanged.", h=0.30, w=0.95)
T += para("**4. Full sequence** -- log excerpt, CREATE_ENTITY then GET_ENTITY, in order (send, receive, process, reply, final client response; request/response bodies shortened; the worker runs in the Docker VM, so its clock differs from the client's -- here the worker's lines are stamped about 0.3 s earlier than the client's send, in other runs a few tens of ms later -- compare the offsets, not the timestamps):")
seq = []
for ln in demo.splitlines():
    if "[client] Sending" in ln or "[client] SENT" in ln or "[from docker logs" in ln or "[client] RECEIVED" in ln or "Response returned" in ln:
        seq.append(re.sub(r" body=.*", " body={...}", ln.replace("[from docker logs s9871-worker] ", "")) if "Response returned" not in ln else ln[:150] + " ...")
T += lst("\n".join(seq), "tiny")

# ------------------------------------------------------------------------------------------------------------------ Part 2
M = (HW / "METRICS.md").read_text(encoding="utf-8")
T += "\\section*{Part 2 -- Three-Agent Kafka Pipeline}\n"
T += para("Planner, Writer and Reviewer run as separate processes and never call each other: each reads one topic and writes the next (`s9871_inbox` -> `s9871_tasks` -> `s9871_drafts` -> `s9871_final`). "
          "The model is qwen3:8b through the HW1 `ModelClient` (thinking off). All three share one consume -> handle -> produce -> commit loop (`run_stage`) and copy the correlation\\_id unchanged. "
          "The four commands of the assignment (`python planner.py`, `writer.py`, `reviewer.py`, `send_question.py`) were run as four separate operating-system processes; each agent's output is saved in its own file, `raw/part2_planner.log`, `part2_writer.log`, `part2_reviewer.log` and `part2_send_question.txt`.".replace("\\\\_", "_").replace("\\_", "_"))
T += "\\subsection*{Topic creation (Kafka CLI)}\n"
cli = [ln for ln in rawtext("part2_topics_cli.txt").splitlines() if ln.startswith(("$ kafka-topics.sh --create", "Created", "$ kafka-topics.sh --list")) or "PartitionCount" in ln]
T += lst("\n".join(re.sub(r"\tTopicId: \S+", "", ln) for ln in cli), "tiny")
T += "\\subsection*{Planner, Writer and Reviewer code}\n"
T += lst(src_of("code/kafka_hw8/planner.py", "SYSTEM") + "\n\n" + src_of("code/kafka_hw8/planner.py", "plan"), "tiny")
T += lst(src_of("code/kafka_hw8/writer.py", "SYSTEM") + "\n\n" + src_of("code/kafka_hw8/writer.py", "write"), "tiny")
T += lst(src_of("code/kafka_hw8/reviewer.py", "SYSTEM") + "\n\n" + src_of("code/kafka_hw8/reviewer.py", "review"), "tiny")
T += para("The shared loop that reads the input topic, calls the handler, produces to the next topic and commits (the handler is the function above; `send_question.py` is the sender):")
T += lst(between("code/kafka_hw8/agent_common.py", "def run_stage", "    def send(topic"), "tiny")
T += "\\subsection*{One complete message journey, inbox to final}\n"
T += para("Each stage's real log lines for one question, in the order they happened (one host, so one clock; message bodies shortened):")
T += lst("\n".join(re.sub(r" body=.*", " body={...}", ln) for ln in rawtext("part2_journey.txt").splitlines() if ln.strip()), "tiny")
T += "\\subsection*{Final message from s9871\\_final}\n"
sq = rawtext("part2_send_question.txt")
T += lst(sq[sq.index("{"):sq.rindex("}") + 1], "scriptsize")
T += "\\subsection*{How Kafka helped the agents coordinate}\n"
T += md_block(metrics_section("Part 2").split("\n", 1)[1])

# ------------------------------------------------------------------------------------------------------------------ Part 3
T += "\\section*{Part 3 -- Failure Behavior}\n"
T += para("Every \"before fix\" below is a real run of the same code with the fix switched off. `HW8_MODE=naive|fixed` (default `fixed`) sets three behaviours of the shared loop; each can also be overridden alone. "
          "The poison-message \"before\" run keeps commit-after, so that only the retry policy differs.")
T += table(["Behaviour", "Fixed", "Naive (before fix)"],
           [["Idempotency", "skip a correlation_id already handled (SQLite store)", "handle every delivery"], ["Offset commit", "after the output message is delivered", "before processing (at-most-once)"],
            ["Poison message", "3 attempts, then `s9871_dead_letter`", "retry forever, never commit"]], "p{1.1in}p{2.8in}p{2.3in}")
T += para("**Disclosure: model-free Writer mode.** To make the failure tests fast and repeatable, the Writer ran with `WRITER_MODE=stub` in every Part 3 test: it skips the qwen3:8b call and sleeps for the message's own `work_s` seconds instead, writing a fixed draft. "
          "Validation, Kafka reads and writes, retries, commits and the idempotency store are the same code as in the real Writer. The Part 2 journey above used the real model, and `verify_hw08.py` runs one real-model journey too. "
          "The Writers in these tests are real processes (the kill test is a hard kill with `taskkill /F`), started by `failure_tests.py`, which resets the topics before each run.")
T += "\\subsection*{Failure table (before / after fix)}\n"
T += md_table(metrics_section("Part 3 - failure table"), "p{1.05in}p{2.7in}p{2.65in}")
T += "\\subsection*{Idempotency, offset-commit, retry/dead-letter and partition-key code}\n"
T += para("Settings and the durable processed-correlation\\_id store:".replace("\\_", "_"))
T += lst(between("code/kafka_hw8/agent_common.py", "DEAD_LETTER =", "sys.path.insert") + "\n\n" + src_of("code/kafka_hw8/agent_common.py", "ProcessedStore"), "tiny")
T += para("The loop body: commit-before (naive), the duplicate check, bounded retries and the dead-letter message, then produce, record the correlation_id and commit-after (fixed):")
T += lst(between("code/kafka_hw8/agent_common.py", '        if COMMIT == "before":', '        out["correlation_id"] = corr') + "\n        ...\n" +
         between("code/kafka_hw8/agent_common.py", '        out["correlation_id"] = corr', "    consumer.close()"), "tiny")
T += para("Partition key (the keyed ordering run sends each message with `key = entity_id`; the unkeyed run sends `key = None`):")
T += lst(between("code/kafka_hw8/failure_tests.py", '    keyed = mode == "keyed"', "    wait_until(lambda: len(read_topic(DRAFTS))") + "\n\n" + src_of("code/kafka_hw8/failure_tests.py", "produce"), "tiny")

T += "\\subsection*{I. Duplicate delivery -- logs}\n"
T += para("The same message (same correlation\\_id, same bytes) is delivered a second time. Before: the Writer does the work twice and emits two drafts. After: the second delivery is logged as a duplicate, with no output and no side effect.".replace("\\_", "_"))
T += para("**Before (naive):**")
T += lst("\n".join(logl("part3_duplicate_naive_writer.log", r"ready|RECEIVED|COMMITTED|WORK start|SENT", body=False)), "tiny")
T += para("**After (fixed):**")
T += lst("\n".join(logl("part3_duplicate_fixed_writer.log", r"ready|RECEIVED|COMMITTED|WORK start|SENT|DUPLICATE", body=False)), "tiny")

T += "\\subsection*{II. Consumer death -- logs (Writer hard-killed 1.5 s into an 8 s job, then restarted)}\n"
T += para("**Before (naive, offset committed before processing):** the broker already counts the message as done, so after the restart nothing arrives and no draft is ever produced.")
T += lst("\n".join(logl("part3_kill_naive_console.txt", r"started Writer|HARD-KILLED|right after the kill") + ["--- writer 1 (killed) ---"] + logl("part3_kill_naive_writer_1_killed.log", body=False, drop="Assigned") +
                   ["--- writer 2 (restarted; nothing received) ---"] + logl("part3_kill_naive_writer_2_restarted.log", body=False, drop="Assigned")), "tiny")
T += para("**After (fixed, offset committed after the draft is delivered):** the offset is still uncommitted at the kill, the restarted Writer receives the same offset again, finishes it, and only then commits.")
T += lst("\n".join(logl("part3_kill_fixed_console.txt", r"started Writer|HARD-KILLED|right after the kill") + ["--- writer 1 (killed) ---"] + logl("part3_kill_fixed_writer_1_killed.log", body=False, drop="Assigned") +
                   ["--- writer 2 (restarted) ---"] + logl("part3_kill_fixed_writer_2_restarted.log", body=False, drop="Assigned")), "tiny")

T += "\\subsection*{III. Poison message -- logs}\n"
T += para("A message with a valid correlation\\_id whose `plan` is null (the Writer rejects it every time) is followed by a good message on the same partition.".replace("\\_", "_"))
pn = logl("part3_poison_naive_writer.log", r"ATTEMPT|RECEIVED|WORK|COMMITTED", body=False)
n_att = sum("ATTEMPT" in ln for ln in pn)
n_json = jload("raw/part3_poison_naive.json")["poison_attempts_logged"]
T += para(f"**Before (naive: retry forever):** {n_json} failed attempts in the 15 s the test waited ({n_att} in the saved log by the time the Writer was stopped); the good message behind it never starts (first and last lines shown).")
T += lst("\n".join(pn[:5] + [f"... ({n_att} ATTEMPT lines in total, no COMMITTED / WORK line for the good message) ..."] + pn[-2:]), "tiny")
T += para("**After (fixed: 3 attempts, then the dead-letter topic):**")
T += lst("\n".join(logl("part3_poison_fixed_writer.log", r"ATTEMPT|RECEIVED|DEAD-LETTERED|COMMITTED|WORK start|SENT", body=False)), "tiny")

T += "\\subsection*{IV. Ordering -- both runs}\n"
od = metrics_section("Part 3 IV")
T += para("20 related messages from `VERIFY_SEED` 269871 (4 fixtures, 1 to 8 updates each, saved in `raw/part3_ordering_messages.json`) go through `s9871_tasks` (2 partitions) to two Writers (A and B) in one consumer group. "
          "Per entity, the numbers are the update sequence numbers in the order the Writers finished them (1, 2, 3, ... is correct).")
T += md_table(od, "p{0.78in}p{0.58in}p{1.4in}p{0.8in}p{1.4in}p{0.7in}", "scriptsize")
for mode, label in (("unkeyed", "**Run 1, no key:**"), ("keyed", "**Run 2, key = entity\\_id:**")):
    T += para(label.replace("\\_", "_") + " (processing order, as logged by the two Writers)")
    T += lst("\n".join(logl(f"part3_ordering_{mode}_console.txt", r"assignments|sending 20") + [ln.replace(",", "  ") for ln in rawtext(f"part3_ordering_{mode}.csv").splitlines()]), "tiny")

T += "\\subsection*{What the numbers show}\n"
T += md_block(metrics_section("What the numbers show").split("\n", 1)[1])
T += "\\subsection*{V. Comparison with the HW2 in-process graph}\n"
T += md_block(metrics_section("Part 3 V").split("\n", 1)[1])

# ------------------------------------------------------------------------------------------------------------------ verification + AI_USE
T += "\\section*{Self-check (verification.json)}\n"
ver = jload("verification.json")
T += para(f"`verify_hw08.py` starts the real stack and runs {ver['total']} objective checks (commit `{ver['commit_hash'][:7]}`, SEED {ver['SEED']}, VERIFY\\_SEED {ver['VERIFY_SEED']}): {ver['passed']}/{ver['total']} passed. ".replace("VERIFY\\_SEED", "VERIFY_SEED") +
          "It was also run against two deliberately broken states and failed where it should (`raw/verify_broken_*.txt`: worker stopped and a file missing -> 4/9 passed; the three fixes switched off -> 8/11 passed, with the duplicate, kill and poison checks failing).")
T += table(["Check", "Result"], [[c["check"].replace("Part 3: ", "Part 3 - "), "PASS" if c["passed"] else "FAIL"] for c in ver["checks"]], "p{5.4in}l", "footnotesize")

ai = (HW / "AI_USE.md").read_text(encoding="utf-8").split("<!-- OPTIONS")[0]
assert "TODO" not in ai, "AI_USE.md still has TODO placeholders"
T += "\\section*{AI\\_USE}\n"
for blk in re.split(r"\n## ", ai)[1:]:
    head, _, body = blk.partition("\n")
    T += f"\\subsection*{{{md(head.strip())}}}\n" + para(body.strip().replace("\n\n", " ").replace("\n", " "))

T += "\\end{document}\n%% Screenshots used by this report (all present in reports/hw08/screenshots/):\n" + "".join(f"%   {f}\n" for f in sorted(set(figs)))
if HASH != "PLACEHOLDER_HASH":
    T = T.replace(r"\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw8 tag) \\", r"\textbf{Tagged commit:} " + HASH + r" (tag: hw8) \\")
    T = T.replace("tree/PLACEHOLDER_HASH", "tree/" + HASH)
OUT.write_text(T, encoding="utf-8", newline="\n")
print("wrote", OUT, len(T.splitlines()), "lines;", len(figs), "figures")
