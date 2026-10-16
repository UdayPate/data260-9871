"""
DATA-260 Homework 6 - Part 4.5: score the consolidation against the known ground truth.
Reads ONLY the committed files: reports/hw06/part4/MEMORY_original_55lines.md,
MEMORY_consolidated.md and ground_truth.json. Writes raw/part4_consolidation_result.json.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "reports" / "hw06"
P4 = ROOT / "part4"
orig = (P4 / "MEMORY_original_55lines.md").read_text(encoding="utf-8")
cons = (P4 / "MEMORY_consolidated.md").read_text(encoding="utf-8")
gt = json.loads((P4 / "ground_truth.json").read_text(encoding="utf-8"))

entries = lambda t: [l for l in re.sub(r"<!--.*?-->", "", t, flags=re.S).splitlines() if l.strip()]
bullets = lambda t: [l[2:].strip() for l in t.splitlines() if l.startswith("- ")]
cons_plain = [b for b in bullets(cons.split("## Conflicts")[0])]
conflict_lines = [b for b in bullets(cons.split("## Conflicts")[1])] if "## Conflicts" in cons else []

res = {"original": {"file_lines": len(orig.splitlines()), "entries": len(entries(orig)), "fact_bullets": len(bullets(orig))},
       "consolidated": {"file_lines": len(cons.splitlines()), "entries": len(entries(cons)),
                        "plain_fact_bullets": len(cons_plain), "conflict_records": len(conflict_lines)},
       "duplicate_groups": [], "conflicts": []}
print(f"original: {res['original']}\nconsolidated: {res['consolidated']}\n")
print("DUPLICATE GROUPS (ground truth) -> how many lines survive as plain facts (1 = fully merged)")
for g in gt["duplicate_groups"]:
    alive = [x for x in g if x in cons_plain]
    newest = max(g)
    row = {"lines_in_group": len(g), "survivors": len(alive), "survivor_is_newest": alive == [newest] if len(alive) == 1 else None,
           "example": g[0][13:70]}
    res["duplicate_groups"].append(row)
    print(f"  {len(g)} lines -> {len(alive)} survive  newest-kept={row['survivor_is_newest']}  ({row['example']}...)")
full = sum(1 for r in res["duplicate_groups"] if r["survivors"] == 1)
res["duplicate_groups_fully_merged"] = f"{full}/{len(gt['duplicate_groups'])}"
print(f"fully merged groups: {res['duplicate_groups_fully_merged']}; lines removed by merging: "
      f"{sum(r['lines_in_group'] - r['survivors'] for r in res['duplicate_groups'])}\n")

print("CONTRADICTIONS (ground truth) -> what the consolidation did")
for c in gt["conflicts"]:
    older_in_conf, newer_in_conf = c["older"] in "\n".join(conflict_lines), c["newer"] in "\n".join(conflict_lines)
    if c["kind"] == "newer-wins":
        ok = any(l.startswith(f'[resolved] kept "{c["newer"]}" over "{c["older"]}"') for l in conflict_lines)
        verdict = "CORRECT: resolved, newer line kept, older recorded" if ok else "INCORRECT/MISSED"
    elif c["kind"] == "ambiguous-same-day":
        ok = any(l.startswith("[unresolved") and older_in_conf and newer_in_conf for l in conflict_lines)
        verdict = "CORRECT: flagged unresolved for the user, both kept" if ok else "INCORRECT/MISSED"
    else:  # trap: newer line is only tentative
        qwen_kept = any("qwen3:8b" in x for x in cons_plain)
        llama_plain = c["newer"] in cons_plain
        ok = False
        verdict = ("NOT FLAGGED: both facts retained as plain lines (qwen3:8b kept, llama3 still marked tentative) - "
                   "nothing wrong was decided and nothing was lost, but the contradiction was not recorded"
                   if qwen_kept and llama_plain else "INCORRECT")
    res["conflicts"].append({"kind": c["kind"], "ok": ok, "verdict": verdict})
    print(f"  [{c['kind']}] {verdict}")
res["contradictions_correctly_handled"] = f"{sum(r['ok'] for r in res['conflicts'])}/{len(gt['conflicts'])}"
res["contradiction_resolved_incorrectly"] = [r["kind"] for r in res["conflicts"] if "INCORRECT" in r["verdict"]]
res["contradiction_not_flagged"] = [r["kind"] for r in res["conflicts"] if "NOT FLAGGED" in r["verdict"]]
unique_lost = [u for u in bullets(orig) if re.search(r"Uday|DATA-260|SEED is|MySQL 8 is|React|Lenovo|all-MiniLM|\.tex|UdayPate|mysqldump|utf-8|fixtures with|SQLAlchemy|Playwright|Postman|PORT_BASE|Redis|reports/hwNN|mcp dev|Windows side|every 6 user|up to 3 facts|DOMAIN_ID 7", u)
               and u not in cons_plain]
res["unique_facts_lost"] = unique_lost
print(f"\nunique (non-duplicate, non-conflicting) facts missing from the consolidated plain list: {len(unique_lost)} {unique_lost}")
(ROOT / "raw" / "part4_consolidation_result.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
