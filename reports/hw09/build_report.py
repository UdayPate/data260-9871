"""
Builds reports/hw09/Patel_HW09_report.tex from the repo's real files (copied from reports/hw08/build_report.py; the helpers are unchanged
except that md() also renders *italic*):
  - code listings are cut out of the source files by name with `ast` (src_of) or between two marker lines (between)
  - tables are filled from METRICS.md / the saved JSON (raw/*.json), log excerpts from the saved raw/*.log and *.txt files
  - text comes from METRICS.md and AI_USE.md
Then compile:  cd reports/hw09 && /home/uday/bin/tectonic -X compile Patel_HW09_report.tex
    python3 reports/hw09/build_report.py
"""
import ast
import json
import re
from pathlib import Path

HW = Path(__file__).resolve().parent                 # reports/hwNN
REPO = HW.parent.parent
RAW = HW / "raw"
OUT = HW / "Patel_HW09_report.tex"
# Leave as PLACEHOLDER_HASH until the final commit is tagged; then set the full 40-character hash of the tag (git rev-parse hwN) and rebuild.
HASH = "210badc829ee0e14ce73ed89de7a09f44e06cb30"

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

\title{DATA-260 Homework 9 -- Report}
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
\textbf{Local model used:} qwen3:8b via Ollama (thinking off; sampling seed 9871 and temperature 0 in Part 4) for the HW8 agent pipeline (Part 2) and the Part 4 Answering Agent; sentence-transformers/all-MiniLM-L6-v2 for the embeddings. \\
\textbf{Cache:} Redis Stack 7.4.0 (\texttt{redis/redis-stack-server}, RediSearch vector index, FLAT, cosine) in docker compose; MySQL \texttt{s9871\_rel}; every Redis key starts with \texttt{s9871:}. \\
\textbf{Repository:} \url{https://github.com/UdayPate/data260-9871} \\
\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw9 tag) \\
{\footnotesize\url{https://github.com/UdayPate/data260-9871/tree/PLACEHOLDER_HASH}} \\
\textbf{Collaborator access:} confirmed working for Sbnikitha and supriyaselvanganesan.

"""

# ------------------------------------------------------------------------------------------------------------------ Part 1
T += "\\section*{Part 1 -- Redis View Counter}\n"
T += para("Reuse: the primary entity is the `fixtures` table of `s9871_rel` (HW4/HW5); it gets a new `views` column (`migrate_hw09.py`). "
          "The one new method is `FixtureCache.increment_fixture_views(fixture_id)` in `code/cache_hw9/fixture_cache.py`: it `INCR`s the key `s9871:views:fixture:<id>` on every access, "
          "and when the count is a multiple of 10 it copies the count to MySQL and logs `Synced views to database`. Redis runs as a new service in the existing `docker-compose.yml`.")
T += lst(src_of("code/cache_hw9/fixture_cache.py", "FixtureCache.increment_fixture_views"), "scriptsize")
T += "\\subsection*{Output of counter\\_demo.py (my own PowerShell, 25 accesses of fixture 5)}\n"
T += lst(rawtext("part1_terminal_demo_output.txt").strip(), "tiny")
T += para("Both syncs fire exactly at accesses 10 and 20. The last two lines are read straight from Redis and MySQL after the run: Redis holds all 25 views, MySQL holds the last synced value (20); views 21-25 reach MySQL at the next multiple of 10.")
T += "\\subsection*{Checked directly in Redis and MySQL, and by tests}\n"
T += lst("\n".join(ln for ln in rawtext("part1_direct_check.txt").splitlines() if "fixture:1" not in ln), "tiny")
T += para("`test_counter.py` (13 checks, real Redis and MySQL; the MySQL value is read after every access) passes 13/13. As a mutation check, syncing at the wrong moment made it fail (10/13); the failing lines:")
T += lst("\n".join(ln for ln in rawtext("part1_mutation_check_output.txt").splitlines() if ln.startswith("[FAIL]") or "checks passed" in ln), "tiny")
T += para("The tests also cover the failure paths: ids 0, -5, '1', None, True and 1.5 raise `ValueError` and create no key; an unknown fixture id keeps counting but logs a warning at the sync and creates no row; with MySQL down the 10th access still returns 10 and logs an error; with Redis down the error reaches the caller.")

# ------------------------------------------------------------------------------------------------------------------ Part 2
P2 = metrics_section("Part 2")
T += "\\section*{Part 2 -- Semantic Response Cache}\n"
T += para("Reuse: on a miss the question goes through the unchanged HW8 Planner/Writer/Reviewer pipeline over Kafka (`pipeline_client.py`), with the fixture facts for any `FX-9871-nnnnn` code in the question prepended from MySQL (`facts.py`). "
          "`CachedQA.ask` (`qa_service.py`) embeds the query with all-MiniLM-L6-v2, finds the nearest cached query with a RediSearch KNN query (FLAT index, cosine; similarity = 1 - distance), "
          "and returns `is_cached`, `similarity` and `latency_ms` with every answer. An entry stores the query, its embedding, the final answer, a status and a data-version marker "
          "(a SHA-256 fingerprint of the fixture facts the answer used; `updated_at` is deliberately not used because it changes on every Part 1 view sync). Only answers the Reviewer approved are cached.")
T += lst(src_of("code/cache_hw9/qa_service.py", "CachedQA.ask"), "tiny")
T += lst(src_of("code/cache_hw9/semantic_cache.py", "SemanticCache.nearest") + "\n\n" + src_of("code/cache_hw9/semantic_cache.py", "SemanticCache.store"), "tiny")
T += para("Test: 13 queries (5 new, 4 exact duplicates, 4 paraphrases), run in my own PowerShell on the real pipeline (qwen3:8b through Kafka); one uncounted warm-up question loaded the model first. "
          "Each log line below is written before the answer is returned.")
T += lst("\n".join(re.sub(r"^(\S+ \S+) \[qa\] ", r"\1 ", ln) for ln in rawtext("part2_cache.log").splitlines()), "tiny")
T += md_table_n(P2, "rlp{2.55in}rlr", "footnotesize", 0)
T += md_table_n(P2, "p{2.6in}p{1.6in}", "small", 1)
T += md_block("\n".join(ln for ln in body_only(P2).splitlines() if not ln.startswith("|")).split("What this shows", 1)[1].join(["What this shows", ""]))

# ------------------------------------------------------------------------------------------------------------------ Part 3
S32 = msub("3.1 / 3.2")
T += "\\section*{Part 3 -- Threshold Economics and Stale Answers}\n"
T += "\\subsection*{3.1 Labeled test set (cache\\_cases.yaml)}\n"
T += para("Committed (commit `1c72c91`) before any threshold was run and not edited afterwards. Ten seed queries sit in the cache; each of the 40 cases is looked up against them. "
          "`validate_cases.py` checks the labels against the database without using any embedding (10/10 checks, and a mutation check caught a case whose answer was not actually different).")
T += lst((REPO / "code/cache_hw9/cache_cases.yaml").read_text(encoding="utf-8"), "tiny")
T += "\\subsection*{3.2 Threshold sweep}\n"
T += md_block("\n".join(ln for ln in nofence(body_only(S32)).splitlines() if not ln.startswith("|")).split("What this shows")[0].strip().split("Where the hits")[0])
T += md_table_n(S32, "p{0.6in}p{1.1in}p{1.9in}p{1.0in}p{0.9in}", "footnotesize", 0)
T += para("Where the hits come from (same run):")
T += md_table_n(S32, "p{0.55in}p{0.8in}p{0.8in}p{1.05in}p{0.95in}p{0.85in}p{0.55in}", "scriptsize", 1)
T += md_block("What this shows" + "\n".join(ln for ln in nofence(body_only(S32)).splitlines() if not ln.startswith("|")).split("What this shows", 1)[1])
T += lst("\n".join(ln for ln in rawtext("part3_terminal_output.txt").splitlines() if ln.startswith(("threshold", "wrote")) or "sweep_part3.py" in ln), "tiny")
S33 = msub("3.3")
T += "\\subsection*{3.3 One false hit in full}\n"
T += md_block(body_only(S33))
S34 = msub("3.4")
T += "\\subsection*{3.4 Cost model and threshold choice}\n"
T += md_block("\n".join(ln for ln in body_only(S34).splitlines() if not ln.startswith("|")))
T += md_table_n(S34, "lll", "small", 0)
T += lst(src_of("code/cache_hw9/cost_model.py", "total_cost"), "scriptsize")
S35 = msub("3.5")
T += "\\subsection*{3.5 Stale answers and invalidation}\n"
T += para("The check added to `CachedQA.ask` (off by default, so Part 2 behaves as measured; `check_version=True` in this demonstration):")
T += lst(between("code/cache_hw9/qa_service.py", "        stale = False", "        if best and similarity >= threshold and not stale"), "scriptsize")
pre, _, post = body_only(S35).partition("\nStrategy:")
T += md_block("\n".join(ln for ln in pre.splitlines() if not ln.startswith("|")))
T += md_table_n(S35, "p{3.1in}p{3.0in}", "scriptsize", 0)
T += md_block("Strategy:" + post)
T += para("Terminal output of `stale_demo.py` (my own PowerShell; the 30+30 timing hits are only in the log file `raw/part3_stale.log`):")
T += lst("\n".join(ln for ln in rawtext("part3_terminal_output.txt").split("stale_demo.py", 1)[1].splitlines()[1:] if "Loading" not in ln), "tiny")
T += para("Mutation check: with the staleness comparison disabled the demo failed steps 6 and 7 (7/9 passed, `raw/part3_stale_mutation_output.txt`).")

# ------------------------------------------------------------------------------------------------------------------ Part 4
D = REPO / "code" / "agents_hw9"
S44, S41, S42, S43, SX = msub("4.4"), msub("4.1"), msub("4.2"), msub("4.3"), msub("Short explanations")
P4 = metrics_section("Part 4")
T += "\\section*{Part 4 -- Self-Improving Multi-Agent System}\n"
T += para(P4.split("\n", 1)[1].split("### 4.4")[0].strip().replace("\n", " "))
T += "\\subsection*{Reference dataset and input files}\n"
ref_lines = (D / "data" / "reference_dataset.json").read_text(encoding="utf-8").splitlines()
T += para("`reference_dataset.json` holds every fixture of `s9871_rel` (5000 rows, one per line; first four shown). The Evaluator reads only this file. "
          "The three input files hold only an id and the question (no expected answers); no fixture appears in more than one of them. They were committed (commit `80fd59a`) before any result existed, and `test_data.json` was used only for the final test.")
T += lst("\n".join(asc_line for asc_line in ref_lines[:10]) + "\n    ...", "tiny")
for name, label in (("training", "training\\_data.json (14)"), ("validation", "validation\\_data.json (14)"), ("test", "test\\_data.json (18)")):
    T += f"\\textbf{{{label}}}\n" + lst(jsonl(D / "data" / f"{name}_data.json"), "tiny")
T += "\\subsection*{The two agents}\n"
T += para("Reuse: `facts.py` from Part 2 gives the Answering Agent the same league facts from MySQL; `src/model_client.py` is the HW6 adapter. Agents exchange plain JSON messages through the controller `run_question` (below).")
T += lst(src_of("code/agents_hw9/agents.py", "AnsweringAgent.answer"), "tiny")
T += lst(src_of("code/agents_hw9/agents.py", "EvaluatorAgent.evaluate"), "tiny")
T += lst(src_of("code/agents_hw9/system.py", "run_question"), "tiny")
T += "\\subsection*{4.1 Evaluator feedback and revision}\n"
T += md_block(body_only(S41))
T += lst(json.dumps({k: v for k, v in jload("raw/part4_demo.json")["revision"].items() if k in ("n_attempts", "final_answer", "final_result")}, indent=2), "scriptsize")
T += "\\subsection*{4.2 Lessons saved and reused}\n"
T += para(body_only(nofence(S42)).split("Kept lesson store")[0].strip().replace("\n", " "))
T += "\\textbf{lessons.json} (kept store, after the demonstration):\n" + lst((D / "lessons.json").read_text(encoding="utf-8"), "tiny")
T += "\\textbf{lessons\\_candidates.json} (all proposed lessons, used by the Lesson Memory variant):\n" + lst((D / "lessons_candidates.json").read_text(encoding="utf-8"), "tiny")
T += para("Reuse demonstration" + nofence(S42).split("Reuse demonstration", 1)[1].strip().replace("\n", " "))
T += "\\subsection*{4.3 Validation before keeping a lesson}\n"
T += md_block("\n".join(ln for ln in body_only(S43).splitlines() if not ln.startswith("|")))
T += md_table_n(S43, "p{0.95in}p{1.3in}p{0.6in}p{0.75in}p{0.7in}p{0.85in}p{0.5in}", "scriptsize", 0)
T += lst(between("code/agents_hw9/run_part4.py", "        checks = {", "        decisions.append"), "scriptsize")
T += "\\subsection*{4.4 Four variants on the final test set}\n"
T += md_block("\n".join(ln for ln in body_only(S44).splitlines() if not ln.startswith("|")).split("A question counts")[0].strip())
T += md_table_n(S44, "p{1.6in}p{1.0in}p{1.0in}p{1.1in}p{1.2in}", "small", 0)
T += para("A question counts as correct when the Evaluator's final verdict is PASS. First-answer failures per variant:")
T += md_table_n(S44, "p{1.4in}p{2.5in}p{1.9in}", "small", 1)
T += md_block("What this shows" + "\n".join(ln for ln in body_only(S44).splitlines() if not ln.startswith("|")).split("What this shows", 1)[1])
T += "\\subsection*{Console output of run\\_part4.py (my own PowerShell)}\n"
T += lst("\n".join(ln for ln in rawtext("part4_terminal_output.txt").splitlines()[:148] if re.search(r"^(PS |==|training|candidate|kept|   |done)|\{'questions", ln) and not ln.startswith("  [")), "tiny")
T += "\\subsection*{Short explanations}\n"
T += md_block(body_only(SX))

# ------------------------------------------------------------------------------------------------------------------ verification + AI_USE
T += "\\section*{Self-check (verification.json)}\n"
ver = jload("verification.json")
T += para(f"`verify_hw09.py` runs the real system and {ver['total']} objective checks (commit `{ver['commit_hash'][:7]}`, SEED {ver['SEED']}, VERIFY_SEED {ver['VERIFY_SEED']}): {ver['passed']}/{ver['total']} passed. "
          "It was also run against three deliberately broken states and failed where it should (`raw/verify_broken_states.txt`: a missing file -> 9/12, Redis stopped -> 7/12, test_data.json edited after commit -> 11/12).")
T += table(["Check", "Result"], [[c["check"].replace("Part ", "P").replace(": ", " - ", 1), "PASS" if c["passed"] else "FAIL"] for c in ver["checks"]], "p{5.4in}l", "footnotesize")

ai = (HW / "AI_USE.md").read_text(encoding="utf-8").split("<!-- OPTIONS")[0]
assert "TODO" not in ai, "AI_USE.md still has TODO placeholders"
T += "\\section*{AI\\_USE}\n"
for blk in re.split(r"\n## ", ai)[1:]:
    head, _, body = blk.partition("\n")
    T += f"\\subsection*{{{md(head.strip())}}}\n" + para(body.strip().replace("\n\n", " ").replace("\n", " "))

T += "\\end{document}\n"
if HASH != "PLACEHOLDER_HASH":
    T = T.replace(r"\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw9 tag) \\", r"\textbf{Tagged commit:} " + HASH + r" (tag: hw9) \\")
    T = T.replace("tree/PLACEHOLDER_HASH", "tree/" + HASH)
OUT.write_text(T, encoding="utf-8", newline="\n")
print("wrote", OUT, len(T.splitlines()), "lines;", len(figs), "figures")
