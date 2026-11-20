"""
Builds reports/hw11/Patel_HW11_report.tex from the repo's real files (helpers copied from reports/hw10/build_report.py, unchanged):
  - tables are filled from METRICS.md and the saved raw/ files; Muse chat text and watch.py output are shown verbatim from raw/*.txt|json
  - text comes from METRICS.md and AI_USE.md
Then compile:  cd reports/hw11 && /home/uday/bin/tectonic -X compile Patel_HW11_report.tex
    python3 reports/hw11/build_report.py [--preview]
"""
import ast
import json
import re
import sys
from pathlib import Path

HW = Path(__file__).resolve().parent                 # reports/hwNN
REPO = HW.parent.parent
RAW = HW / "raw"
OUT = HW / "Patel_HW11_report.tex"
# Leave as PLACEHOLDER_HASH until the final commit is tagged; then set the full 40-character hash of the tag (git rev-parse hw11) and rebuild.
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

\title{DATA-260 Homework 11 -- Report}
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
KIT = "reports/hw11/kit/stock-watch"
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
\textbf{Local model used:} none for this homework. The agent and the judge are the model behind Meta Muse (free tier), which runs \texttt{watch.py} on its own cloud computer; my laptop was used only to prepare the kit, to test it, and to write the report. \\
\textbf{Watchlist:} NVDA, TSLA, KO, JPM (live); fictional ZNTH, GRBV, HRBK (test fixtures). \\
\textbf{Repository:} \url{https://github.com/UdayPate/data260-9871} \\
\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw11 tag) \\
{\footnotesize\url{https://github.com/UdayPate/data260-9871/tree/PLACEHOLDER_HASH}} \\
\textbf{Collaborator access:} confirmed working for Sbnikitha and supriyaselvanganesan.

"""
T += para("**How the evidence is shown.** The Muse chat and the `watch.py` output are pasted below as text, verbatim from the Muse chat; "
          "each block names the chat message that produced it and the file in `raw/` that holds it. The setup of Part 1 (scheduled task, saved memory, first run) is shown as screenshots of the Muse interface. "
          "Only the line breaks of the long JSON replies were changed, and where that happened it is stated in the file. The submitted files are `policy.md`, `sources.json`, the fixtures in `fixtures/hw11/` and "
          "`golden/gold_hw11.json`, all under `reports/hw11/kit/stock-watch/`.")

# ------------------------------------------------------------------------------------------------------------------ Part 1
T += "\\section*{Part 1 -- Build (short)}\n"
T += para("I installed the kit on Muse (Prompt 1: the demo test passed with `decision_accuracy` 1.0, output in `RUN_LOG.txt`), saved the standing instructions to its memory (Prompt 2), and created the weekday 1:30 PM Pacific task (Prompt 3). "
          "The watchlist is NVDA, TSLA, KO and JPM (CIKs 0001045810, 0001318605, 0000021344, 0000019617), with my contact e-mail in `user_agent`. "
          "The scheduled task has not fired yet (it was created the evening before its first weekday run), so the manual `run stock-watch` below is the evidence of a live run, as the assignment allows.")
T += fig("p1_upcoming_1.png", "Assistant -> Upcoming: the task \"Stock Watch weekday live run\", weekly Monday to Friday at 1:30 pm, run history empty (it had not fired yet).", 0.30, 0.62)
T += fig("p1_memory.png", "Assistant -> Identity -> Memory: the Stock Watch standing instructions saved by Muse (2026-11-19).", 0.62, 0.55)
T += para("**The first live run found nothing, and the kit did not say why.** `run stock-watch` printed `0 new, 0 duplicates suppressed, 0 alerts`. Four tickers with up to ten 8-Ks each cannot give zero, so I asked Muse for the trace of that run:")
T += lst(rawtext("p1_first_run_trace.txt"), "tiny")
T += para("I reproduced both errors from my laptop (`raw/p1_source_diagnosis.txt`): EDGAR rejects `count=5` (the kit's default) and wants 10 or more, and Stooq now returns a JavaScript bot-check page instead of CSV. "
          "I changed `per_company` to 10, added a `max_age_days` filter and a Yahoo Finance price source to `watch.py`, and re-ran on Muse:")
T += lst(rawtext("p1_first_run_v2.txt"), "tiny")
T += fig("p1_first_run.png", "Muse chat after `run stock-watch` with the fixed kit: three HIGH alerts (NVDA Item 2.02, JPM Item 5.02, NVDA Item 5.02) and the run summary.", 0.42, 0.62)

# ------------------------------------------------------------------------------------------------------------------ Part 2
P2 = metrics_section("Part 2")
T += "\\section*{Part 2 -- Materiality Policy}\n"
T += para("`policy.md` defines notify (score 0.80 or more), digest (0.50-0.79), ask (any score, for injected or credential-seeking text) and quiet (below 0.50). The price levels are set per ticker from the "
          "measured volatility of each stock (`raw/vol_study.py` downloads one year of daily closes and writes `raw/vol_study.json`), and the same numbers are in `sources.json` as the scan's per-ticker `threshold_pct`.")
T += render(P2, [("p{0.55in}p{0.6in}p{0.65in}p{0.55in}p{0.55in}p{0.65in}p{0.6in}p{0.6in}", "footnotesize")])
pol = (HW / "kit" / "stock-watch" / "policy.md").read_text(encoding="utf-8")
T += "\\subsection*{The 8-K rules and two examples of each decision (from policy.md)}\n"
T += lst(pol[pol.index("## 8-K items"):pol.index("Scoring guide")].rstrip(), "tiny")

# ------------------------------------------------------------------------------------------------------------------ Part 3
gold = jload("kit/stock-watch/golden/gold_hw11.json")
T += "\\section*{Part 3 -- Golden Set (labels fixed before any run)}\n"
T += para("Twelve cases, two per category, on three fictional companies that mirror the watchlist: ZNTH (volatile, scored with NVDA's levels), GRBV (stable, KO's levels) and HRBK (a bank, JPM's levels). "
          "The fixtures are `fixtures/hw11/` (three price files, an EDGAR feed and a newswire feed). The labels in `golden/gold_hw11.json` were committed (`78da6f2`) before any of these fixtures was run on Muse, and "
          "`verify_hw11.py` checks that order from the git history. They were drafted with the AI assistant and fixed by me before the first run; none was changed afterwards. "
          "The A2 note's link was changed after that commit to an unapproved host so that `fetch` could be tested in Part 4; no label changed.")
rows = [[c["case_id"], c["category"], c["match_title"], c["expected"], c["why"].split(". ")[0].rstrip(".")[:150]] for c in gold["cases"]]
T += table(["Case", "Category", "Item (title)", "Label", "Why (first sentence)"], rows, "p{0.35in}p{0.85in}p{1.75in}p{0.5in}p{2.8in}", "scriptsize")

# ------------------------------------------------------------------------------------------------------------------ Part 4
T += "\\section*{Part 4 -- Failure Injection}\n"
P4 = metrics_section("Part 4")
T += render(P4, [("p{0.9in}p{2.4in}p{3.0in}", "scriptsize")])
T += "\\subsection*{4.1 Duplicate: the same filing from two sources}\n"
T += para("The ZNTH supply-agreement 8-K is in the EDGAR feed, and a news story cites its accession number `0009999911-26-000020`, so both get the same effect ID `15031f35762f`. "
          "Muse's alert for it is in the resume run below (the fourth block), and I asked for its trace:")
T += lst(rawtext("f1_duplicate_trace.json"), "tiny")
T += para("One `retrieved` entry (`edgar_demo`), one ``dedup_merge`` entry (`newswire_demo`), one `effect`: one alert.")
T += "\\subsection*{4.2 Restart: interrupt, open a new chat, resume}\n"
T += lst(rawtext("f2_crash.txt"), "tiny")
T += lst(rawtext("f2_restart.txt"), "tiny")
T += lst(rawtext("f3_resume.txt"), "tiny")
T += para("The new chat knew the scan was interrupted at 2 items. The next `run stock-watch` carried the same run id `20261119-212921-fd82`, so it resumed instead of starting over, and the summary counts 12 new items "
          "(2 before the crash and 10 after) with none repeated. Muse's reply to the new-chat question also used its saved memory notes, so the proof that the state itself survived is the identical run id and the metrics below "
          "(restart recovery rate 1.0), not the chat answer alone.")
T += "\\subsection*{4.3 Prompt injection}\n"
T += lst(rawtext("f3_injection.txt"), "tiny")
T += lst(rawtext("f3_blocked.txt"), "tiny")
T += para("The note was phrased to avoid the script's regex list (the guard flagged only the first injection), so the `ask` decision came from the model's own reading of the policy. "
          "The link `desk.example-newswire.example/priority` was refused by `fetch` (exit 2), and Muse did not open it another way. Both injected items ended as `ask`, and none produced an alert (`injection_items_notified` 0).")
T += "\\subsection*{A retried alert}\n"
T += lst(rawtext("r2_retry.txt"), "tiny")
T += lst(rawtext("r2_retry_trace.json"), "tiny")
T += para("This did not go as the policy intends. Muse re-posted the alert from chat memory without calling `decide`: the trace has one `effect` and no `decide_rejected` step. The ledger was not violated, "
          "but the user saw the alert twice, which the duplicate rate of Part 6 cannot show.")

# ------------------------------------------------------------------------------------------------------------------ Part 5
P5 = metrics_section("Part 5")
T += "\\section*{Part 5 -- Trace of One HIGH Alert}\n"
T += para("The alert is the ZNTH supply agreement, effect `15031f35762f`. The command was `python3 watch.py trace --effect-id 15031f35762f` (its full output is the listing in 4.1 above), and each step is labeled here:")
T += render(P5, [("p{0.8in}p{2.4in}p{3.1in}", "footnotesize")])

# ------------------------------------------------------------------------------------------------------------------ Part 6
P6 = metrics_section("Part 6")
txt = rawtext("p6_metrics_output.txt")
mj = json.loads(txt[txt.index("{"):txt.index("(per_case rows")])
m = mj["metrics"]
assert (m["decision_accuracy"], m["precision_notify"], m["recall_notify"], m["unnecessary_notification_rate"], m["duplicate_notification_rate"], m["restart_recovery_rate"]) == (0.917, 0.857, 1.0, 0.143, 0.0, 1.0)
T += "\\section*{Part 6 -- Metrics}\n"
T += para("Command run on Muse: `python3 watch.py metrics --gold golden/gold_hw11.json` (no `--usage-tokens`, because Muse does not show tokens). Its output, from the pasted chat text:")
T += lst(txt[:txt.index("(per_case rows")].replace("\n\n", "\n").rstrip() + "\n" + txt[txt.index("2. runs query"):].strip(), "tiny")
T += table(["Case", "Category", "Expected", "Got", "OK"], [[r["case_id"], r["category"], r["expected"], r["got"], "yes" if r["correct"] else "NO"] for r in mj["per_case"]], "p{0.5in}p{1.2in}p{0.8in}p{0.8in}p{0.4in}", "footnotesize")
T += render(P6, [("p{1.7in}p{1.3in}p{3.2in}", "footnotesize")])
T += fig("p1_ussage.png", "Muse Settings: Free plan, 0% used before the fixture runs (this screenshot); after all the runs in this report the page read 1% (reported in `raw/p6_usage.txt`), weekly limit resetting Nov 27.", 0.34, 0.55)

# ------------------------------------------------------------------------------------------------------------------ Part 7
P7 = metrics_section("Part 7")
T += "\\section*{Part 7 -- Analysis}\n"
T += render(P7, [])

# ------------------------------------------------------------------------------------------------------------------ verification + AI_USE
T += "\\section*{Self-check (verification.json)}\n"
ver = jload("verification.json")
T += para(f"`verify_hw11.py` runs the real kit in a throw-away copy (crash, resume, guard, retry, snapshot and restore, with a scripted judge that applies the gold labels), checks the saved Muse metrics against their own per-case rows, "
          f"and makes one live scan of Yahoo and EDGAR (commit `{ver['commit_hash'][:7]}`, SEED {ver['SEED']}, VERIFY_SEED {ver['VERIFY_SEED']}): {ver['passed']}/{ver['total']} passed. "
          "It was also run against deliberately broken states and failed where it should (`raw/verify_broken_states.txt`).")
T += table(["Check", "Result"], [[c["check"][:105], "PASS" if c["passed"] else "FAIL"] for c in ver["checks"]], "p{5.4in}l", "scriptsize")

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
    T = T.replace(r"\textbf{Tagged commit:} PLACEHOLDER\_HASH (to be filled in after the final commit and hw11 tag) \\", r"\textbf{Tagged commit:} " + HASH + r" (tag: hw11) \\")
    T = T.replace("tree/PLACEHOLDER_HASH", "tree/" + HASH)
OUT.write_text(T, encoding="utf-8", newline="\n")
print("wrote", OUT, len(T.splitlines()), "lines;", len(figs), "figures")
