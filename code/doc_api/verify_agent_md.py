"""
DATA-260 Homework 6 - Part 4.4: generate a function with AGENT.md in the system prompt and VERIFY that it
follows AGENT.md's rules - by AST analysis and by actually running it - and compare with a control run
that has no AGENT.md. The request itself never mentions type hints, docstrings, naming or logging, so any
compliance has to come from AGENT.md.

AGENT.md rules checked (numbers match AGENT.md):
  3  type hints on every parameter and the return value, plus a one-line docstring
  4  snake_case names, function under 25 lines
  6  no eval()/exec(), no bare `except:`, no print()
Usage: python verify_agent_md.py [runs_per_condition]
"""

import ast
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import config
import file_memory
import llm

TASK = ("Write a Python function that takes a list of fixture dictionaries (each has the keys 'fixture_name', "
        "'category' and 'match_date') and a category string, and returns the fixtures in that category "
        "(ignoring upper/lower case), sorted by 'match_date' ascending. Reply with only the code in a single "
        "```python block.")
SAMPLE = [{"fixture_name": "A", "category": "Soccer", "match_date": "2026-11-02"},
          {"fixture_name": "B", "category": "Cricket", "match_date": "2026-11-01"},
          {"fixture_name": "C", "category": "soccer", "match_date": "2026-11-01"}]
RAW = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw"


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, flags=re.S)
    return (m.group(1) if m else text).strip()


def check_rules(code: str) -> dict:
    """AST-check one generated snippet against AGENT.md rules 3, 4 and 6."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"parses": False, "error": str(exc)}
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    r = {"parses": True, "n_functions": len(funcs)}
    if not funcs:
        return {**r, "error": "no function defined"}
    snake = lambda name: re.fullmatch(r"[a-z_][a-z0-9_]*", name) is not None
    r["names"] = [f.name for f in funcs]
    r["rule4_snake_case"] = all(snake(f.name) for f in funcs)
    r["rule4_under_25_lines"] = all(f.end_lineno - f.lineno + 1 < 25 for f in funcs)
    r["max_function_lines"] = max(f.end_lineno - f.lineno + 1 for f in funcs)

    def hinted(f):
        args = f.args.posonlyargs + f.args.args + f.args.kwonlyargs
        if f.args.vararg: args.append(f.args.vararg)
        if f.args.kwarg: args.append(f.args.kwarg)
        return all(a.annotation is not None for a in args if a.arg not in ("self", "cls")) and f.returns is not None
    r["rule3_type_hints"] = all(hinted(f) for f in funcs)
    def one_line_doc(f: ast.FunctionDef) -> bool:
        """Docstring exists AND its literal sits on a single source line (not a 3-line triple-quote block)."""
        first = f.body[0] if f.body else None
        return (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str) and first.lineno == first.end_lineno)
    r["rule3_one_line_docstring"] = all(one_line_doc(f) for f in funcs)
    calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    r["rule6_no_eval_exec"] = not any(c in ("eval", "exec") for c in calls)
    r["rule6_no_print"] = "print" not in calls
    r["rule6_no_bare_except"] = not any(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree))
    r["all_rules_followed"] = all(v for k, v in r.items() if k.startswith("rule"))
    return r


def run_behaviour(code: str) -> dict:
    """Execute the generated function on SAMPLE (only if it imports nothing risky)."""
    tree = ast.parse(code)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    bad = [ast.unparse(n) for n in imports if not (isinstance(n, ast.ImportFrom) and n.module in ("typing", "__future__"))]
    if bad:
        return {"executed": False, "reason": f"skipped: imports {bad}"}
    ns: dict = {}
    exec(compile(tree, "<generated>", "exec"), ns)          # test harness only; generated code was AST-screened
    fn = next(v for k, v in ns.items() if callable(v) and getattr(v, "__module__", None) is None or k in
              [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
    fn = ns[[n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)][0]]
    out = fn([dict(x) for x in SAMPLE], "SOCCER")
    ok = [x["fixture_name"] for x in out] == ["C", "A"]
    return {"executed": True, "result_names": [x["fixture_name"] for x in out], "correct": ok}


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    agent_prompt = file_memory.build_system_prompt(file_memory.load_agent(), file_memory.load_memory())
    conditions = {"with_AGENT_md": agent_prompt, "control_no_AGENT_md": "You are a helpful assistant."}
    report = {"generated": datetime.now().isoformat(timespec="seconds"), "task": TASK, "runs_per_condition": runs,
              "conditions": {}}
    print("Run at", report["generated"], "| runs per condition:", runs)
    for name, system in conditions.items():
        rows = []
        for i in range(runs):
            config.settings["LLM_SEED"] = 9871 + i
            text = llm.complete([{"role": "system", "content": system}, {"role": "user", "content": TASK}])["text"]
            code = extract_code(text)
            rules = check_rules(code)
            beh = run_behaviour(code) if rules.get("parses") and rules.get("n_functions") else {"executed": False}
            rows.append({"seed": 9871 + i, "code": code, "rules": rules, "behaviour": beh})
            failed = [k for k, v in rules.items() if k.startswith("rule") and not v]
            print(f"\n[{name} seed={9871 + i}] all_rules={rules.get('all_rules_followed')} failed={failed} "
                  f"behaviour_correct={beh.get('correct')}\n{code}")
        n_ok = sum(1 for r in rows if r["rules"].get("all_rules_followed"))
        per_rule = {k: sum(1 for r in rows if r["rules"].get(k)) for k in rows[0]["rules"] if k.startswith("rule")}
        report["conditions"][name] = {"runs": rows, "followed_all_rules": n_ok, "per_rule_pass_counts": per_rule,
                                      "behaviour_correct": sum(1 for r in rows if r["behaviour"].get("correct"))}
        print(f"\n>>> {name}: followed ALL rules in {n_ok}/{runs} runs; per-rule passes {per_rule}; "
              f"behaviour correct in {report['conditions'][name]['behaviour_correct']}/{runs}")

    # review mode (AGENT.md rule 8): the answer must be ONLY bullets
    config.settings["LLM_SEED"] = 9871
    review = llm.complete([{"role": "system", "content": agent_prompt},
                           {"role": "user", "content": "Review this code:\n\ndef run(cmd):\n    return eval(cmd)\n"}])["text"]
    lines = [l for l in review.splitlines() if l.strip()]
    only_bullets = bool(lines) and all(l.lstrip().startswith(("-", "*", "\u2022")) for l in lines)
    report["review_mode"] = {"answer": review, "only_bullets": only_bullets, "mentions_eval": "eval" in review.lower()}
    print("\nReview-mode answer:\n" + review + f"\n>>> only bullets: {only_bullets}; mentions eval: {'eval' in review.lower()}")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "part4_agent_md_verification.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
