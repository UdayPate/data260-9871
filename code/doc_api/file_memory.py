"""
DATA-260 Homework 6 - Part 4: file-based memory (AGENT.md + MEMORY.md).

AGENT.md  = durable project / agent instructions (human-written).
MEMORY.md = durable facts learned from conversations, one dated bullet per line, with the
            last-consolidated time in an HTML comment on the first line:
            <!-- last-consolidated: 2026-10-15T09:00:00-07:00 -->

Both files are loaded into the system prompt on every turn. Commands: /memory, /compact,
/dream, /help. Consolidation never silently deletes: the model must account for every
numbered input line, anything it fails to account for is re-added verbatim, a backup is
written first, and contradictions are recorded in an explicit "## Conflicts" section.
"""

import json
import logging
import os
import re
import shutil
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import llm

log = logging.getLogger("file_memory")

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_STAMP_RE = re.compile(r"<!--\s*last-consolidated:\s*([^\s|]+)\s*(?:\|\s*entries:\s*(\d+))?\s*-->")
_FACT_RE = re.compile(r"^-\s+(.*\S)\s*$")
CONFLICTS_HEADING = "## Conflicts"

# rolling recent conversation (in process memory) that /dream mines for durable facts
recent_messages: deque = deque(maxlen=20)


# --------------------------------------------------------------------------
# Loading + prompt construction
# --------------------------------------------------------------------------
def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def load_agent(path: str | None = None) -> str:
    """Return AGENT.md text ('' if the file is missing)."""
    return _read(path or config.AGENT_PATH)


def load_memory(path: str | None = None) -> str:
    """Return MEMORY.md text ('' if the file is missing)."""
    return _read(path or config.MEMORY_PATH)


def build_system_prompt(agent_text: str, memory_text: str) -> str:
    """Compose the system prompt: AGENT.md instructions, then MEMORY.md facts."""
    parts = []
    if agent_text.strip():
        parts.append("# Standing instructions (AGENT.md)\n" + _COMMENT_RE.sub("", agent_text).strip())
    if memory_text.strip():
        parts.append("# Remembered facts (MEMORY.md)\n" + _COMMENT_RE.sub("", memory_text).strip())
    return "\n\n".join(parts) if parts else "You are a helpful assistant."


# --------------------------------------------------------------------------
# Consolidation triggers
# --------------------------------------------------------------------------
def entry_lines(text: str) -> list[str]:
    """Non-empty, non-comment lines (the unit the 40-line rule counts)."""
    stripped = _COMMENT_RE.sub("", text)
    return [ln.rstrip() for ln in stripped.splitlines() if ln.strip()]


def read_last_consolidated(text: str) -> datetime | None:
    """Parse the last-consolidated timestamp; None if absent or malformed."""
    m = _STAMP_RE.search(text)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(m.group(1))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def read_consolidated_entries(text: str) -> int | None:
    """Entry count recorded by the last consolidation ('entries: N' in the stamp), if any."""
    m = _STAMP_RE.search(text)
    return int(m.group(2)) if m and m.group(2) else None


def consolidation_needed(text: str, now: datetime | None = None) -> tuple[bool, str]:
    """True if >MEMORY_MAX_LINES entries, or last-consolidated is >24h old/unknown."""
    now = now or datetime.now(timezone.utc)
    n = len(entry_lines(text))
    if n > config.MEMORY_MAX_LINES:
        return True, f"{n} entries > {config.MEMORY_MAX_LINES}"
    ts = read_last_consolidated(text)
    if ts is None:
        return (True, "no valid last-consolidated timestamp") if n else (False, "memory is empty")
    age = now - ts
    if age > timedelta(hours=config.MEMORY_MAX_AGE_HOURS):
        return True, f"last consolidated {age.total_seconds() / 3600:.1f}h ago > {config.MEMORY_MAX_AGE_HOURS}h"
    return False, f"{n} entries, consolidated {age.total_seconds() / 3600:.1f}h ago"


# --------------------------------------------------------------------------
# Consolidation
# --------------------------------------------------------------------------
def _norm(s: str) -> str:
    s = re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", s.lower())
    return " ".join(re.sub(r"[^a-z0-9 ]+", "", s).split())


def split_sections(text: str) -> tuple[list[str], list[str]]:
    """(fact bullet lines, existing conflict bullet lines). Facts come from above the '## Conflicts'
    heading; conflict records below it are NOT facts and are never re-judged - they are carried forward."""
    facts, conflicts, in_conflicts = [], [], False
    for ln in entry_lines(text):
        if ln.strip() == CONFLICTS_HEADING:
            in_conflicts = True
        elif (m := _FACT_RE.match(ln)):
            (conflicts if in_conflicts else facts).append(ln.strip() if in_conflicts else m.group(1))
    return facts, conflicts


def _fact_lines(text: str) -> list[str]:
    return split_sections(text)[0]


_TOPIC_PROMPT = (
    "Give each numbered fact a SHORT topic key (2-4 lowercase words) naming WHAT the fact is about, so that "
    "two facts about the same thing get the same key even if worded differently or if they disagree. "
    "Examples: 'local model', 'mongodb database name', 'git commit policy', 'reminder preference', "
    "'game start time'. Reply with ONLY JSON like {{\"1\": \"key\", \"2\": \"key\"}}.\n\nFACTS:\n{numbered}"
)

_PAIR_PROMPT = (
    "Do these two memory facts say the same thing, contradict each other, or neither?\n"
    '- "same": both state the same fact, only worded differently\n'
    '- "contradict": they are about the same thing but cannot both be true\n'
    '- "neither": they are about different things, or both can be true\n'
    "Examples:\n"
    'A: Meetings are on Mondays. / B: We meet every Monday. -> {{"relation": "same"}}\n'
    'A: The office is in Austin. / B: The office is in Denver. -> {{"relation": "contradict"}}\n'
    'A: The office is in Austin. / B: Lunch is at noon. -> {{"relation": "neither"}}\n'
    "Now answer for:\nA: {a}\nB: {b}\nReply with ONLY JSON like {{\"relation\": \"same\"}}."
)
_TENTATIVE_PROMPT = (
    "Is this memory fact tentative, hypothetical or undecided (for example it says 'considering', 'maybe', "
    "'might', 'thinking about', 'no decision yet'), as opposed to a settled fact?\nFact: {fact}\n"
    'Reply with ONLY JSON like {{"tentative": true}} or {{"tentative": false}}.'
)
_RELATIONS = {"same", "contradict", "neither"}
_ID_RE = re.compile(r"[a-z0-9_:\-]*\d[a-z0-9_:\-]*|[a-z0-9]+_[a-z0-9_]+")


def _identifiers(fact: str) -> set[str]:
    """Identifier-like tokens (contain a digit or underscore): s9871_rel, 9am, qwen3:8b ..."""
    return set(_ID_RE.findall(_strip_date(fact).lower().replace(".", " ").replace(",", " ")))


def differing_identifiers(a: str, b: str) -> tuple[set[str], set[str]]:
    ia, ib = _identifiers(a), _identifiers(b)
    return ia - ib, ib - ia


KEY_SIM = 0.70    # topic-key similarity that puts two facts in one cluster
TEXT_SIM = 0.70   # fact-text similarity that puts two facts in one cluster


def _json_object(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw, flags=re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _strip_date(f: str) -> str:
    return re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", f)


def _date_of(f: str) -> str:
    m = re.match(r"^\[(\d{4}-\d{2}-\d{2})\]", f)
    return m.group(1) if m else ""


def _topic_keys(facts: list[str]) -> dict[int, str]:
    """One model call labels every fact with a short topic key (empty dict on failure)."""
    numbered = "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1))
    data = _json_object(llm.complete([{"role": "user", "content": _TOPIC_PROMPT.format(numbered=numbered)}])["text"])
    out = {}
    for k, v in (data or {}).items():
        if str(k).isdigit() and 1 <= int(k) <= len(facts) and isinstance(v, str):
            out[int(k) - 1] = v.strip().lower()
    return out


def cluster_facts(facts: list[str]) -> list[list[int]]:
    """Group candidate duplicate/conflicting facts (0-based indexes). Two facts share a cluster if
    their topic keys match or are similar, or their texts are similar (union-find over pairs)."""
    import embeddings
    keys = _topic_keys(facts)
    key_vec = [embeddings.embed(keys.get(i) or _strip_date(f)) for i, f in enumerate(facts)]
    txt_vec = [embeddings.embed(_strip_date(f)) for f in facts]
    parent = list(range(len(facts)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    dot = lambda u, v: sum(a * b for a, b in zip(u, v))
    for a in range(len(facts)):
        for b in range(a + 1, len(facts)):
            same_key = a in keys and b in keys and keys[a] == keys[b]
            if same_key or dot(key_vec[a], key_vec[b]) >= KEY_SIM or dot(txt_vec[a], txt_vec[b]) >= TEXT_SIM:
                parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(len(facts)):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def _ask_json(prompt: str) -> dict | None:
    for _ in (1, 2):
        data = _json_object(llm.complete([{"role": "user", "content": prompt}])["text"])
        if data is not None:
            return data
    return None


def _judge_pair(older: str, newer: str) -> dict:
    """Classify ONE pair. The model only says same / contradict / neither (and whether the newer fact is
    tentative); the resolution RULES are applied here, in code:
      newer fact wins, unless it is tentative (older stays) or both carry the same date (unresolved)."""
    data = _ask_json(_PAIR_PROMPT.format(a=older, b=newer))
    if not data or data.get("relation") not in _RELATIONS:
        return {"relation": "distinct", "reason": "model gave no usable answer; both kept", "judged": False}
    rel = data["relation"]
    only_a, only_b = differing_identifiers(older, newer)
    if rel == "same" and only_a and only_b:
        # guard: a "same" verdict whose two sides each carry an identifier the other lacks
        # (s9871_db vs s9871_rel, 9am vs 10am) is a contradiction - never merge it away
        rel = "contradict"
        guard_note = f"model said same but values differ ({', '.join(sorted(only_a))} vs {', '.join(sorted(only_b))}); "
    else:
        guard_note = ""
    guarded = bool(guard_note)
    if rel == "same":
        return {"relation": "duplicate", "reason": "same fact", "judged": True, "guarded": False}
    if rel == "neither":
        return {"relation": "distinct", "reason": "compatible or unrelated", "judged": True, "guarded": False}
    if _date_of(older) == _date_of(newer):
        return {"relation": "unresolved", "judged": True, "guarded": guarded,
                "reason": guard_note + "same date, nothing says which is right"}
    tent = _ask_json(_TENTATIVE_PROMPT.format(fact=_strip_date(newer)))
    if tent and tent.get("tentative") is True:
        return {"relation": "older_stays", "judged": True, "guarded": guarded,
                "reason": guard_note + "the newer fact is tentative, so the established older fact stays"}
    return {"relation": "newer_replaces_older", "judged": True, "guarded": guarded,
            "reason": guard_note + "newer settled fact replaces the older one"}


def _judge_cluster(facts: list[str], members: list[int]) -> dict:
    """Judge every pair inside one small cluster (0-based indexes)."""
    dups, confs, judged_all, guarded = [], [], True, 0
    order = sorted(members, key=lambda i: (_date_of(facts[i]), i))
    for x in range(len(order)):
        for y in range(x + 1, len(order)):
            old_i, new_i = order[x], order[y]
            r = _judge_pair(facts[old_i], facts[new_i])
            judged_all &= r["judged"]
            guarded += r.get("guarded", False)
            if r["relation"] == "duplicate":
                dups.append([old_i, new_i])
            elif r["relation"] in ("newer_replaces_older", "older_stays", "unresolved"):
                keep = {"newer_replaces_older": new_i, "older_stays": old_i, "unresolved": None}[r["relation"]]
                confs.append({"between": [old_i, new_i], "keep": keep,
                              "status": "resolved" if keep is not None else "unresolved", "reason": r["reason"]})
    return {"duplicate_groups": dups, "conflicts": confs, "judged": judged_all, "guarded": guarded}


def _dedupe_only(facts: list[str]) -> dict:
    """Deterministic fallback (no model): merge exact/near-exact duplicates, keep the newest line."""
    seen: dict[str, list[int]] = {}
    for i, f in enumerate(facts):
        seen.setdefault(_norm(f), []).append(i)
    return {"duplicate_groups": [g for g in seen.values() if len(g) > 1], "conflicts": [], "judged": False}


def consolidate(path: str | None = None, use_llm: bool = True) -> dict:
    """Consolidate MEMORY.md in place. Returns an audit report (counts, merges, conflicts, backup)."""
    path = path or config.MEMORY_PATH
    text = load_memory(path)
    before_entries = len(entry_lines(text))
    facts, old_conflict_lines = split_sections(text)
    if not facts:
        return {"changed": False, "before": before_entries, "after": before_entries,
                "message": "nothing to consolidate (no fact lines)"}

    method, dup_groups, conflicts, unjudged, guarded = "llm", [], [], 0, 0
    try:
        if not use_llm:
            raise llm.LLMError("model disabled")
        for members in cluster_facts(facts):
            res = _judge_cluster(facts, members)
            unjudged += 0 if res["judged"] else 1
            guarded += res["guarded"]
            dup_groups += res["duplicate_groups"]
            conflicts += res["conflicts"]
    except llm.LLMError:
        method = "dedupe-only fallback (model unavailable)"
        res = _dedupe_only(facts)
        dup_groups = [[g[0], j] for g in res["duplicate_groups"] for j in g[1:]]
        conflicts = []

    # ---- merge duplicate PAIRS into groups (union-find); the kept line is the newest-dated member's own text
    par = list(range(len(facts)))

    def find(x: int) -> int:
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for a_i, b_i in dup_groups:
        par[find(a_i)] = find(b_i)
    comp: dict[int, list[int]] = {}
    for i in range(len(facts)):
        comp.setdefault(find(i), []).append(i)
    rep = list(range(len(facts)))
    merges = []
    for g in comp.values():
        if len(g) < 2:
            continue
        best = max(g, key=lambda i: (_date_of(facts[i]), i))
        for i in g:
            rep[i] = best
        merges.append({"kept": facts[best], "merged_lines": [facts[i] for i in g if i != best]})

    # ---- conflicts operate on representatives; conflict members live ONLY in the Conflicts section
    in_conflict: set[int] = set()
    conflict_lines, conflict_report, seen_pairs = [], [], set()
    for c in conflicts:
        members = sorted({rep[i] for i in c["between"]})
        if len(members) < 2 or tuple(members) in seen_pairs:
            continue
        seen_pairs.add(tuple(members))
        in_conflict.update(members)
        kept = rep[c["keep"]] if c["keep"] is not None else None
        dropped = [m for m in members if m != kept]
        if kept is not None:
            line = (f"- [resolved] kept \"{facts[kept]}\" over \"{'; '.join(facts[m] for m in dropped)}\" "
                    f"({c['reason']})")
        else:
            line = (f"- [unresolved - needs the user] \"{'\" vs \"'.join(facts[m] for m in members)}\" "
                    f"({c['reason']})")
        conflict_lines.append(line)
        conflict_report.append({**c, "kept_text": facts[kept] if kept is not None else None,
                                "texts": [facts[m] for m in members]})

    out = ["__STAMP__", "# Project memory"]
    emitted: set[int] = set()
    for i in range(len(facts)):
        r = rep[i]
        if r in emitted or r in in_conflict:
            continue
        emitted.add(r)
        out.append(f"- {facts[r]}")
    all_conflict_lines = old_conflict_lines + [c for c in conflict_lines if c not in old_conflict_lines]
    if all_conflict_lines:
        out.append(CONFLICTS_HEADING)
        out += all_conflict_lines

    after_entries = len(entry_lines("\n".join(out[1:])))
    out[0] = (f"<!-- last-consolidated: {datetime.now().astimezone().isoformat(timespec='seconds')}"
              f" | entries: {after_entries} -->")

    backup = Path(config.MEMORY_BACKUP_DIR)
    backup.mkdir(parents=True, exist_ok=True)
    backup_path = backup / f"MEMORY-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    if Path(path).exists():
        shutil.copy2(path, backup_path)          # the original always survives in a backup
    tmp = Path(str(path) + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)                        # single atomic write
    return {"changed": True, "carried_forward_conflicts": len(old_conflict_lines), "method": method,
            "before": before_entries, "after": after_entries,
            "merges": merges, "conflicts": conflict_report, "clusters_not_fully_judged": unjudged, "guard_overrides": guarded,
            "backup": str(backup_path), "still_over_limit": after_entries > config.MEMORY_MAX_LINES}


# --------------------------------------------------------------------------
# /dream: mine recent conversation for durable facts
# --------------------------------------------------------------------------
def parse_string_list(raw: str, limit: int = 5) -> list[str]:
    """Pull a list of short strings out of model output. Accepts one JSON array, SEVERAL arrays on separate
    lines (qwen3 sometimes does this), or falls back to nothing. Duplicates are dropped."""
    m = re.search(r"\[.*\]", raw, flags=re.S)
    items: list = []
    if m:
        try:
            items = json.loads(m.group(0))
        except json.JSONDecodeError:
            for chunk in re.findall(r"\[[^\[\]]*\]", raw):
                try:
                    items += json.loads(chunk)
                except json.JSONDecodeError:
                    continue
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        t = str(it).strip()
        if t and _norm(t) not in seen:
            seen.add(_norm(t))
            out.append(t)
    return out[:limit]


_DREAM_PROMPT = (
    "From the conversation below, list up to 5 DURABLE long-term facts worth remembering about the "
    "user, their projects or their preferences. Skip small talk, one-off questions and anything "
    "already obviously temporary. Reply with ONLY a JSON array of short sentences, e.g. "
    '["The user prefers email reminders."]. Reply [] if there is nothing durable.\n\nConversation:\n{convo}'
)


def dream(path: str | None = None, messages: list[dict] | None = None) -> dict:
    """Identify durable facts in recent conversation and append new ones to MEMORY.md."""
    path = path or config.MEMORY_PATH
    msgs = list(messages if messages is not None else recent_messages)
    if not msgs:
        return {"added": [], "skipped": [], "message": "no recent conversation to learn from"}
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    raw = llm.complete([{"role": "user", "content": _DREAM_PROMPT.format(convo=convo)}])["text"]
    items = parse_string_list(raw)
    text = load_memory(path)
    known = {_norm(f) for f in _fact_lines(text)}
    today = datetime.now().strftime("%Y-%m-%d")
    added, skipped = [], []
    for it in items if isinstance(items, list) else []:
        fact = str(it).strip()
        if not fact:
            continue
        if _norm(fact) in known:
            skipped.append(fact)
            continue
        added.append(f"[{today}] {fact}")
        known.add(_norm(fact))
    if added:
        body = text if text.strip() else (
            f"<!-- last-consolidated: {datetime.now().astimezone().isoformat(timespec='seconds')} -->\n# Project memory\n")
        lines = body.rstrip("\n").split("\n")
        at = next((i for i, ln in enumerate(lines) if ln.strip() == CONFLICTS_HEADING), len(lines))
        lines[at:at] = [f"- {a}" for a in added]      # new facts go above the '## Conflicts' section
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"added": added, "skipped": skipped}


# --------------------------------------------------------------------------
# Command / chat handling
# --------------------------------------------------------------------------
HELP_TEXT = (
    "Commands:\n"
    "  /memory  - show the current file-based memory (AGENT.md + MEMORY.md, entry count, consolidation status)\n"
    "  /compact - consolidate MEMORY.md (merge duplicates, resolve contradictions explicitly) and report entry counts before and after\n"
    "  /dream   - mine the recent conversation for durable facts and add the new ones to MEMORY.md\n"
    "  /help    - show this message\n"
    "Anything else is sent to the model with AGENT.md + MEMORY.md in the system prompt."
)


def cmd_memory() -> str:
    agent, mem = load_agent(), load_memory()
    needed, why = consolidation_needed(mem)
    ts = read_last_consolidated(mem)
    return (f"=== AGENT.md ({len(entry_lines(agent))} lines) ===\n{agent.strip() or '(missing or empty)'}\n\n"
            f"=== MEMORY.md ({len(entry_lines(mem))} entries; last consolidated: "
            f"{ts.isoformat() if ts else 'unknown'}; consolidation needed: {needed} - {why}) ===\n"
            f"{mem.strip() or '(missing or empty)'}")


def cmd_compact() -> str:
    r = consolidate()
    if not r["changed"]:
        return r["message"]
    lines = [f"MEMORY.md consolidated via {r['method']}: entries before = {r['before']}, after = {r['after']}"
             f"{'  (STILL over the limit)' if r['still_over_limit'] else ''}",
             f"Duplicate groups merged: {len(r['merges'])}; conflicts recorded: {len(r['conflicts'])}; "
             f"clusters not fully judged: {r['clusters_not_fully_judged']}; guard overrides: {r['guard_overrides']}; backup: {r['backup']}"]
    for m in r["merges"]:
        lines.append(f"  MERGED into: {m['kept']}")
        lines += [f"      absorbed: {x}" for x in m["merged_lines"]]
    for c in r["conflicts"]:
        lines.append(f"  conflict [{c['status']}]: " + " | ".join(c["texts"]) + f" -> {c['reason']}")
    return "\n".join(lines)


def cmd_dream() -> str:
    r = dream()
    if r.get("message"):
        return r["message"]
    return (f"/dream added {len(r['added'])} fact(s), skipped {len(r['skipped'])} already known.\n"
            + "\n".join(f"  + {a}" for a in r["added"]))


COMMANDS = {"/memory": cmd_memory, "/compact": cmd_compact, "/dream": cmd_dream,
            "/help": lambda: HELP_TEXT}


def chat_turn(message: str) -> dict:
    """One file-memory turn: run a command, or answer with AGENT.md + MEMORY.md in the system prompt."""
    msg = message.strip()
    if msg.startswith("/"):
        name = msg.split()[0].lower()
        if name not in COMMANDS:
            return {"command": name, "unknown_command": True,
                    "output": f"Unknown command {name}.\n{HELP_TEXT}"}
        return {"command": name, "output": COMMANDS[name]()}

    auto, warning = None, None
    mem = load_memory()
    needed, why = consolidation_needed(mem)
    if needed:
        n, last_n, ts = len(entry_lines(mem)), read_consolidated_entries(mem), read_last_consolidated(mem)
        fresh = ts is not None and datetime.now(timezone.utc) - ts <= timedelta(hours=config.MEMORY_MAX_AGE_HOURS)
        if n > config.MEMORY_MAX_LINES and fresh and last_n is not None and n <= last_n:
            # already consolidated and nothing was added since: re-running cannot shrink it, so don't loop
            warning = (f"MEMORY.md still has {n} entries (limit {config.MEMORY_MAX_LINES}) after its last "
                       f"consolidation and nothing new was added; prune facts by hand to get under the limit.")
        else:
            auto = {"reason": why, **{k: v for k, v in consolidate().items() if k in ("method", "before", "after")}}
    system = build_system_prompt(load_agent(), load_memory())
    msgs = [{"role": "system", "content": system}] + list(recent_messages) + [{"role": "user", "content": msg}]
    result = llm.complete(msgs)
    recent_messages.append({"role": "user", "content": msg})
    recent_messages.append({"role": "assistant", "content": result["text"]})
    return {"command": None, "reply": result["text"], "auto_consolidated": auto, "memory_warning": warning,
            "prompt_tokens": result["prompt_tokens"], "completion_tokens": result["completion_tokens"]}
