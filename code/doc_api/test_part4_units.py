"""
DATA-260 Homework 6 - Part 4: deterministic checks of the file-memory helpers
(no model needed): loading, entry counting, timestamp parsing, consolidation triggers.
Includes cases that MUST say "no consolidation" and malformed input.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import file_memory as fm

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
stamp = lambda dt: f"<!-- last-consolidated: {dt.isoformat()} -->"
bullets = lambda n: "\n".join(f"- [2026-10-01] fact number {i}" for i in range(n))

recent = stamp(now - timedelta(hours=1))
check("40 entries + fresh timestamp -> NOT needed", not fm.consolidation_needed(f"{recent}\n{bullets(40)}\n", now)[0])
check("41 entries + fresh timestamp -> needed (line rule)", fm.consolidation_needed(f"{recent}\n{bullets(41)}\n", now)[0])
check("comments and blank lines are not counted",
      fm.consolidation_needed(f"{recent}\n<!-- a note -->\n\n\n{bullets(40)}\n\n<!-- end -->\n", now)[0] is False)
check("block comment spanning lines not counted", len(fm.entry_lines("<!--\nline a\nline b\n-->\n- x\n")) == 1)
needed, why = fm.consolidation_needed(f"{stamp(now - timedelta(hours=25))}\n{bullets(3)}\n", now)
check("3 entries but timestamp 25h old -> needed (age rule)", needed and "25.0h" in why)
check("timestamp 23h old -> NOT needed", not fm.consolidation_needed(f"{stamp(now - timedelta(hours=23))}\n{bullets(3)}\n", now)[0])
needed, why = fm.consolidation_needed("# Project memory\n- a fact\n", now)
check("missing timestamp with entries -> needed", needed and "no valid" in why)
needed, why = fm.consolidation_needed("<!-- last-consolidated: not-a-date -->\n- a fact\n", now)
check("malformed timestamp with entries -> needed (treated as unknown)", needed)
check("empty memory -> NOT needed", not fm.consolidation_needed("", now)[0])
check("timestamp without tz is read as UTC", fm.read_last_consolidated("<!-- last-consolidated: 2026-10-15T09:00:00 -->").tzinfo is not None)
check("read_last_consolidated(absent) is None", fm.read_last_consolidated("- a fact") is None)

with tempfile.TemporaryDirectory() as d:
    missing = str(Path(d) / "nope.md")
    check("load_memory(missing file) == ''", fm.load_memory(missing) == "")
    check("load_agent(missing file) == ''", fm.load_agent(missing) == "")
agent, mem = fm.load_agent(), fm.load_memory()
prompt = fm.build_system_prompt(agent, mem)
check("system prompt contains AGENT.md instructions", "Never use eval()" in prompt and "# Standing instructions (AGENT.md)" in prompt)
check("system prompt contains MEMORY.md facts", "qwen3:8b" in prompt and "# Remembered facts (MEMORY.md)" in prompt)
check("HTML comments stripped from the prompt", "last-consolidated" not in prompt)
check("fallback prompt when both files empty", fm.build_system_prompt("", "") == "You are a helpful assistant.")
dd = fm._dedupe_only(["[2026-09-01] Model is qwen3:8b.", "[2026-10-01] model is  qwen3:8b", "[2026-09-02] Other fact."])
check("dedupe-only fallback groups near-identical lines (indexes 0 and 1) and leaves the distinct one", dd["duplicate_groups"] == [[0, 1]])
bad = fm._json_object("sorry, here is no json")
check("unusable model output parses to None (-> fallback)", bad is None)

# ---- regressions for bugs found while testing Part 4
check("parse_string_list: one JSON array", fm.parse_string_list('["a fact", "b fact"]') == ["a fact", "b fact"])
multi = '["The user prefers Neovim."]  \n["The user is vegetarian."]\n["The user is vegetarian."]'
check("parse_string_list: several arrays on separate lines (qwen3 quirk) are all kept, duplicates dropped",
      fm.parse_string_list(multi) == ["The user prefers Neovim.", "The user is vegetarian."])
check("parse_string_list: garbage -> []", fm.parse_string_list("no list here") == [])
sec = "<!-- last-consolidated: 2026-10-15T09:00:00-07:00 | entries: 4 -->\n# Project memory\n- [2026-10-01] fact A\n## Conflicts\n- [resolved] kept \"x\" over \"y\" (r)\n"
facts_, confs_ = fm.split_sections(sec)
check("conflict-section lines are NOT treated as facts", facts_ == ["[2026-10-01] fact A"] and len(confs_) == 1)
check("stamp with '| entries: N' parses (timestamp and count)",
      fm.read_last_consolidated(sec) is not None and fm.read_consolidated_entries(sec) == 4)
check("old stamp format (no entries) still parses", fm.read_consolidated_entries("<!-- last-consolidated: 2026-10-15T09:00:00-07:00 -->\n") is None)
with tempfile.TemporaryDirectory() as d:
    mp = Path(d) / "MEMORY.md"
    mp.write_text(sec, encoding="utf-8")
    r = fm.dream(str(mp), [{"role": "user", "content": "x"}]) if False else None
    # dream() inserts ABOVE the Conflicts heading (call its writer path via a stub model answer)
    import llm as _llm
    _orig = _llm.complete
    _llm.complete = lambda msgs: {"text": '["The user likes tea."]', "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
    try:
        r = fm.dream(str(mp), [{"role": "user", "content": "I like tea"}])
    finally:
        _llm.complete = _orig
    lines = mp.read_text(encoding="utf-8").splitlines()
    check("/dream inserts new facts above '## Conflicts'", any("likes tea" in l for l in lines) and
          next(i for i, l in enumerate(lines) if "likes tea" in l) < lines.index("## Conflicts"))
    r2 = None
    _llm.complete = lambda msgs: {"text": '["The user likes tea."]', "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
    try:
        r2 = fm.dream(str(mp), [{"role": "user", "content": "I like tea"}])
    finally:
        _llm.complete = _orig
    check("/dream skips a fact that is already known", r2["added"] == [] and len(r2["skipped"]) == 1)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
