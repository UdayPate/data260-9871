"""
DATA-260 Homework 7 - Part 6: one combined test run.

  (a) integration: three small Python files in a temporary sandbox; ONE instruction; the agent must glob, then search, then read, and show the file
      that contains DEBUG (real model: qwen3:8b through the Part 2 hand-written agent loop, with the six file tools)
  (b) safety gate: five commands that must pass and five that must be blocked (pure Python, no model)

Run from the repo root, inside the venv:   python code/run_part6_test.py
"""

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_loop import run_agent  # noqa: E402
from file_tools import TOOL_SPECS, FileTools, confirm_bash, is_destructive, make_executor, make_sandbox  # noqa: E402

SYSTEM = ("You are a coding assistant working inside a sandbox directory. Use the tools to look things up: list files with glob_files, find text with "
          "search_in_files, read a file with read_file. Never guess file names or file contents; answer only from what the tools returned.")
INSTRUCTION = "Find which Python file in the sandbox contains the word DEBUG and show me that file's full contents."
FILES = {
    "app.py": "def main():\n    print('starting')\n\nif __name__ == '__main__':\n    main()\n",
    "settings.py": "DEBUG = True\nPORT = 8871\n\ndef show():\n    if DEBUG:\n        print('debug mode on, port', PORT)\n",
    "helpers.py": "def add(a, b):\n    return a + b\n",
}
MUST_PASS = ["ls -la", "cat notes.txt", "grep -n DEBUG app.py", "git status", "echo hello"]
MUST_BLOCK = ["rm -rf ./build", "sudo apt install foo", "chmod 777 app.py", "dd if=/dev/zero of=/dev/sda", "ls -la; rm -rf /"]

print("Run at", time.strftime("%Y-%m-%dT%H:%M:%S"))
failures = []

print("\n" + "=" * 100 + "\n(a) INTEGRATION: glob -> search -> read, one instruction, real model\n" + "=" * 100)
sandbox = make_sandbox()
try:
    tools = FileTools(sandbox)
    for name, text in FILES.items():
        tools.write_file(name, text)
    print(f"sandbox: {sandbox}\nfiles created: {', '.join(FILES)}\nuser> {INSTRUCTION}\n")
    run = run_agent(INSTRUCTION, tool_specs=TOOL_SPECS, executor=make_executor(tools), system_prompt=SYSTEM, log_path=sandbox / "run.jsonl", verbose=True)
    order = [t["tool"] for t in run["trace"] if t["valid"]]
    answer = run["final_answer"] or ""
    in_order = False
    if "glob_files" in order and "search_in_files" in order and "read_file" in order:
        in_order = order.index("glob_files") < order.index("search_in_files") < len(order) - 1 - order[::-1].index("read_file")
    found = "DEBUG = True" in answer and "settings.py" in answer
    print(f"\ntool order: {' -> '.join(order)}")
    print(f"[{'PASS' if in_order else 'FAIL'}] used glob_files, then search_in_files, then read_file")
    print(f"[{'PASS' if found else 'FAIL'}] the answer names settings.py and shows its contents (DEBUG = True)")
    print(f"[{'PASS' if run['stop_reason'] == 'final_answer' else 'FAIL'}] stop_reason = {run['stop_reason']} ({run['steps']} steps, {run['latency_ms'] / 1000:.1f} s of model time)")
    if not (in_order and found and run["stop_reason"] == "final_answer"):
        failures.append("integration")
finally:
    shutil.rmtree(sandbox, ignore_errors=True)

print("\n" + "=" * 100 + "\n(b) SAFETY GATE: 5 commands that must pass, 5 that must be blocked (pure Python, no model)\n" + "=" * 100)
print(f"{'command':<34} {'expected':<8} {'result':<8} {'is_destructive':<15} reason")
for expected, commands in (("pass", MUST_PASS), ("block", MUST_BLOCK)):
    for c in commands:
        d = confirm_bash(c)
        result = "allowed" if d["allowed"] else "blocked"
        ok = (result == "allowed") == (expected == "pass")
        if not ok:
            failures.append(c)
        print(f"{c:<34} {expected:<8} {result:<8} {str(is_destructive(c)):<15} {d['reason']}  [{'OK' if ok else 'WRONG'}]")
false_allows = [c for c in MUST_BLOCK if confirm_bash(c)["allowed"]]
print(f"\nfalse allows (a command that should be blocked but was allowed): {false_allows or 'none'}")
print("\nRESULT:", "ALL PASSED" if not failures else f"FAILED: {failures}")
sys.exit(1 if failures else 0)
