"""
DATA-260 Homework 6 - Part 4 live test of the file-based memory system over real HTTP.
The server must be started with FILE_MEMORY_PATH / FILE_MEMORY_BACKUP_DIR pointing at a throwaway copy
of reports/hw06/part4/MEMORY_original_55lines.md (the live MEMORY.md is never touched).
Usage: python test_part4.py <memory_file> <backup_dir> <ground_truth.json>
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8871"
mem_path, backup_dir, gt_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
gt = json.loads(gt_path.read_text(encoding="utf-8"))
results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def chat(msg):
    return requests.post(f"{BASE}/api/file-chat", json={"message": msg}, timeout=600)


facts_in = lambda text: [l[2:].strip() for l in text.splitlines() if l.startswith("- ")]
print("Run at", datetime.now().isoformat(timespec="seconds"))
original = mem_path.read_text(encoding="utf-8")
orig_facts = facts_in(original)
print(f"original file: {len(original.splitlines())} lines, {len(orig_facts)} fact lines")

# ---------- state + trigger
st = requests.get(f"{BASE}/api/file-memory").json()
print("GET /api/file-memory ->", st)
check("55-line file reports 54 entries and consolidation needed", st["entries"] == 54 and st["consolidation_needed"])

# ---------- /help, /memory, unknown command, validation failures
r = chat("/help").json(); print("\n/help ->\n" + r["output"])
check("/help lists /memory /compact /dream /help", all(c in r["output"] for c in ("/memory", "/compact", "/dream", "/help")))
r = chat("/memory").json()
print("\n/memory ->\n" + r["output"][:900] + "\n  ...[truncated for log]")
check("/memory shows AGENT.md and MEMORY.md with entry count",
      "AGENT.md" in r["output"] and "MEMORY.md (54 entries" in r["output"] and "consolidation needed: True" in r["output"])
r = chat("/nope"); print("\n/nope ->", r.status_code, r.json()["output"][:60])
check("unknown command is reported (not sent to the model)", r.json().get("unknown_command") is True)
check("empty message -> 422", requests.post(f"{BASE}/api/file-chat", json={"message": ""}).status_code == 422)
check("extra field -> 422", requests.post(f"{BASE}/api/file-chat", json={"message": "hi", "x": 1}).status_code == 422)

# ---------- /compact on the 55-line file
r = chat("/compact"); out = r.json()["output"]
print("\n/compact ->\n" + out)
after_text = mem_path.read_text(encoding="utf-8")
after_facts = facts_in(after_text)
m = re.search(r"entries before = (\d+), after = (\d+)", out)
check("/compact reports before and after counts", bool(m) and int(m.group(1)) == 54)
n_after = int(m.group(2)) if m else 999
file_lines = len(after_text.splitlines())
print(f"after: {file_lines} file lines, {n_after} entries (non-empty, non-comment)")
check("consolidated file has fewer than 40 lines (wc -l)", file_lines < 40)
entries_now = [l for l in re.sub(r"<!--.*?-->", "", after_text, flags=re.S).splitlines() if l.strip()]
check("consolidated entry count < 40 and equals the reported 'after'", n_after < 40 and len(entries_now) == n_after)
check("a backup of the ORIGINAL 55-line file was written",
      any(p.read_text(encoding="utf-8") == original for p in backup_dir.glob("MEMORY-*.md")))

# accounting: every original fact line is kept verbatim, listed as 'absorbed' (merged), or quoted in a conflict line
absorbed = {l.split("absorbed: ", 1)[1].strip() for l in out.splitlines() if "absorbed: " in l}
conflict_text = "\n".join(l for l in after_text.splitlines() if l.startswith("- [resolved") or l.startswith("- [unresolved"))
unaccounted = [f for f in orig_facts if f not in after_facts and f not in absorbed and f not in conflict_text]
print("original lines NOT accounted for:", unaccounted)
check("no original fact line silently disappeared (kept / merged-and-listed / in a conflict line)", not unaccounted)

# duplicates: each ground-truth duplicate group should collapse; count survivors
print("\nDuplicate groups (ground truth) -> surviving plain lines:")
for g in gt["duplicate_groups"]:
    alive = [x for x in g if x in after_facts]
    print(f"  {len(g)} lines -> {len(alive)} survive")
collapsed = sum(1 for g in gt["duplicate_groups"] if sum(x in after_facts for x in g) <= 1)
check("at least 3 duplicate groups merged to a single line", collapsed >= 3)
survivors = {i: [x for x in g if x in after_facts] for i, g in enumerate(gt["duplicate_groups"])}
check("every merged group's surviving line is its NEWEST-dated line",
      all(sv == [max(g)] for g, sv in zip(gt["duplicate_groups"], survivors.values()) if len(sv) == 1))

# contradictions: explicit section, nothing deleted
check("an explicit '## Conflicts' section exists", "## Conflicts" in after_text)
print("\nGround-truth contradictions vs result:")
verdicts = {}
for c in gt["conflicts"]:
    old_t, new_t = c["older"], c["newer"]
    in_conf = old_t in conflict_text and new_t in conflict_text
    both_plain = old_t in after_facts and new_t in after_facts
    verdicts[c["kind"]] = "recorded in Conflicts" if in_conf else ("both kept as plain facts, NOT flagged" if both_plain else "see file")
    print(f"  [{c['kind']}] -> {verdicts[c['kind']]}\n      expected: {c['correct_resolution']}")
for c in gt["conflicts"]:
    check(f"neither side of the '{c['kind']}' contradiction was lost (in the file, or merged-and-listed)",
          all(x in after_text or x in absorbed for x in (c["older"], c["newer"])))
nw = [c for c in gt["conflicts"] if c["kind"] == "newer-wins"]
check("both 'newer-wins' contradictions recorded as resolved, keeping the NEWER line",
      all(f'- [resolved] kept "{c["newer"]}" over "{c["older"]}"' in after_text for c in nw))
amb = [c for c in gt["conflicts"] if c["kind"] == "ambiguous-same-day"][0]
check("same-day contradiction flagged UNRESOLVED for the user (not silently picked)",
      "[unresolved" in after_text and amb["older"] in after_text and amb["newer"] in after_text)

# idempotence: a second /compact must not lose facts
before2 = set(facts_in(after_text))
out2 = chat("/compact").json()["output"]; print("\nsecond /compact ->\n" + out2.splitlines()[0])
after2 = mem_path.read_text(encoding="utf-8")
check("second /compact keeps every fact line (idempotent, nothing lost)",
      all(f in after2 or f in out2 for f in before2))
conf_before = [l for l in after_text.splitlines() if l.startswith("- [resolved") or l.startswith("- [unresolved")]
conf_after = [l for l in after2.splitlines() if l.startswith("- [resolved") or l.startswith("- [unresolved")]
check("second /compact carries all 3 conflict records forward verbatim, with no nesting",
      conf_after == conf_before and len(conf_after) == 3 and not any('"- [' in l or 'kept "[resolved' in l for l in conf_after))

# ---------- /dream: real conversation, then mine it
chat("My favorite code editor is Neovim, and I always use it on Linux.")
chat("How is the weather today?")
chat("I'm vegetarian, so please never suggest meat dishes for team dinners.")
size_before = len(facts_in(mem_path.read_text(encoding="utf-8")))
r = chat("/dream"); print("\n/dream ->\n" + r.json()["output"])
mem_after_dream = mem_path.read_text(encoding="utf-8")
added = [l for l in facts_in(mem_after_dream) if re.search(r"neovim|vegetarian", l, re.I)]
today = datetime.now().strftime("%Y-%m-%d")
check("/dream added at least one durable fact from the conversation (Neovim / vegetarian)", len(added) >= 1)
check("/dream facts are date-stamped with today", all(a.startswith(f"[{today}]") for a in added))
check("/dream did not add small talk (weather)", not any("weather" in l.lower() for l in facts_in(mem_after_dream)))
n1 = len(facts_in(mem_after_dream))
chat("/dream")
check("running /dream again does not add duplicates", len(facts_in(mem_path.read_text(encoding="utf-8"))) == n1)

# ---------- automatic consolidation triggers on a normal chat turn
consolidated_text = mem_path.read_text(encoding="utf-8")        # a clean, consolidated, <40-entry state
DISTINCT = ["The club mascot is a golden lion named Leo.", "Pre-game warm-ups start forty minutes before kickoff.",
            "The league newsletter is sent on the first of each month.", "Spare jerseys are stored in the blue equipment bag.",
            "The clubhouse key is kept with the groundskeeper.", "Water bottles are refilled at the north tap.",
            "Parking is free on weekends behind the library.", "The trophy cabinet is in the main hallway.",
            "Lost property is collected in a box by the gate.", "Referees are booked through the regional office.",
            "The first-aid room is next to the changing rooms.", "End-of-season awards are held in the school hall."]
mem_path.write_text(consolidated_text + "".join(f"- [2026-10-15] {t}\n" for t in DISTINCT), encoding="utf-8")
n_pre = len(facts_in(mem_path.read_text(encoding="utf-8")))
r = chat("Say hello in five words.").json()
print("\nauto trigger (line count) ->", r.get("auto_consolidated"), "| warning:", r.get("memory_warning"))
check("a normal turn auto-consolidates when MEMORY.md exceeds 40 entries (and still replies)",
      r.get("auto_consolidated") and "entries >" in r["auto_consolidated"]["reason"] and bool(r.get("reply")))
txt = mem_path.read_text(encoding="utf-8")
check("auto-consolidation kept all 12 distinct facts (nothing deleted)", all(t in txt for t in DISTINCT))
r = chat("Say hello in five words.").json()
print("second turn, nothing new added ->", r.get("auto_consolidated"), "| warning:", r.get("memory_warning"))
check("no re-consolidation loop: file still >40 but nothing new -> warning instead of another run",
      r.get("auto_consolidated") is None and r.get("memory_warning") and "prune" in r["memory_warning"])

# age rule from a clean small file
old_stamp = (datetime.now().astimezone() - timedelta(hours=30)).isoformat(timespec="seconds")
mem_path.write_text(re.sub(r"<!-- last-consolidated:.*?-->", f"<!-- last-consolidated: {old_stamp} -->", consolidated_text),
                    encoding="utf-8")
r = chat("Say hello in five words.").json()
print("auto trigger (age) ->", r.get("auto_consolidated"))
check("a normal turn auto-consolidates when the timestamp is >24h old",
      r.get("auto_consolidated") and "h ago" in r["auto_consolidated"]["reason"])
r = chat("Say hello in five words.").json()
check("no consolidation when memory is small and fresh", r.get("auto_consolidated") is None and r.get("memory_warning") is None)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
for n in failed: print("FAILED:", n)
sys.exit(1 if failed else 0)
