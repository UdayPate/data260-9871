"""
DATA-260 Homework 7 - Part 6: tests of the six file tools and the safety gate. No model, no network.

Everything that touches files runs inside a temporary sandbox directory that is deleted at the end.
Run from the repo root, inside the venv:   python code/test_file_tools.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_loop import run_agent  # noqa: E402
from file_tools import (SAFE_PREFIXES, TOOL_SPECS, FileTools, ToolError, confirm_bash, destructive_reason, is_destructive,  # noqa: E402
                        make_executor, make_sandbox)

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"   ({extra})" if extra and not cond else ""), flush=True)


def raises(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except ToolError as e:
        return str(e)
    return None


SANDBOX = make_sandbox()
T = FileTools(SANDBOX)

try:
    # ------------------------------------------------------------------ read_file / write_file / edit_file
    print("### read_file, write_file, edit_file")
    w = T.write_file("notes/todo.txt", "line1\nline2\nline3\nline4\nline5\n")
    check("write_file creates the file and its parent directory", w == {"path": "notes/todo.txt", "bytes": 30, "created": True}, str(w))
    check("write_file on an existing file overwrites it (created=False)", T.write_file("notes/todo.txt", "a\nb\nc\nd\ne\n")["created"] is False)
    T.write_file("notes/todo.txt", "line1\nline2\nline3\nline4\nline5\n")
    r = T.read_file("notes/todo.txt")
    check("read_file returns the content and the line counts", r["content"] == "line1\nline2\nline3\nline4\nline5" and r["total_lines"] == 5 and not r["truncated"], str(r))
    r = T.read_file("notes/todo.txt", max_lines=2)
    check("read_file max_lines=2 returns exactly 2 lines and says it was truncated", r["content"] == "line1\nline2" and r["lines_returned"] == 2 and r["total_lines"] == 5 and r["truncated"], str(r))
    check("max_lines larger than the file is not truncated", not T.read_file("notes/todo.txt", max_lines=50)["truncated"])
    check("read_file on a missing file is a reportable error", "no such file" in (raises(T.read_file, "nope.txt") or ""))
    e = T.edit_file("notes/todo.txt", "line3", "THREE")
    check("edit_file replaces the text and the file really changed", "THREE" in T.read_file("notes/todo.txt")["content"] and "line3" not in T.read_file("notes/todo.txt")["content"])
    check("edit_file returns a short unified diff with the removed and added lines", "-line3" in e["diff"] and "+THREE" in e["diff"] and e["diff"].startswith("--- a/notes/todo.txt"), e["diff"])
    check("the diff is short (at most 40 lines plus a marker)", len(e["diff"].splitlines()) <= 41)
    check("edit_file with text that is not there fails and changes nothing", "not found" in (raises(T.edit_file, "notes/todo.txt", "absent", "x") or ""))
    T.write_file("dup.txt", "x\nx\n")
    check("edit_file with text that appears twice is refused (must match exactly once)", "2 times" in (raises(T.edit_file, "dup.txt", "x", "y") or "") and T.read_file("dup.txt")["content"] == "x\nx")
    check("edit_file on a missing file is an error", "no such file" in (raises(T.edit_file, "ghost.txt", "a", "b") or ""))

    # ------------------------------------------------------------------ glob_files / search_in_files
    print("\n### glob_files, search_in_files")
    T.write_file("src/a.py", "print('a')\n")
    T.write_file("src/b.py", "DEBUG = True\nprint('b')\n")
    T.write_file("src/pkg/c.py", "# debug is lowercase here\nx = 1\n")
    T.write_file("src/readme.txt", "DEBUG notes\n")
    g = T.glob_files("**/*.py")
    check("glob_files '**/*.py' finds every python file recursively, sorted", g["files"] == ["src/a.py", "src/b.py", "src/pkg/c.py"], str(g))
    check("glob_files '*.txt' only matches at the top level", T.glob_files("*.txt")["files"] == ["dup.txt"])
    check("glob_files with no match returns an empty list, not an error", T.glob_files("*.zzz")["files"] == [])
    s = T.search_in_files("DEBUG")
    check("search_in_files finds DEBUG in both b.py and readme.txt, with line numbers", {(m["file"], m["line"]) for m in s["matches"]} == {("src/b.py", 1), ("src/readme.txt", 1)}, str(s["matches"]))
    s = T.search_in_files("DEBUG", file_pattern="*.py")
    check("file_pattern='*.py' restricts the search to python files", [m["file"] for m in s["matches"]] == ["src/b.py"], str(s["matches"]))
    check("search is case-sensitive by default and supports regular expressions", T.search_in_files("(?i)debug", "*.py")["count"] == 2 and T.search_in_files(r"^x = \d$", "*.py")["count"] == 1)
    check("an invalid regular expression is a reportable error", "invalid regular expression" in (raises(T.search_in_files, "([") or ""))
    (SANDBOX / "bin.dat").write_bytes(b"\xff\xfe\x00DEBUG\x80")
    check("binary files are skipped, not crashed on", all(m["file"] != "bin.dat" for m in T.search_in_files("DEBUG")["matches"]))

    # ------------------------------------------------------------------ the sandbox boundary
    print("\n### paths cannot escape the sandbox")
    outside = SANDBOX.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    for label, call in [("read ../", lambda: T.read_file("../outside_secret.txt")), ("read absolute path", lambda: T.read_file(str(outside))),
                        ("write ../", lambda: T.write_file("../evil.txt", "x")), ("edit ../", lambda: T.edit_file("../outside_secret.txt", "secret", "x")),
                        ("glob ../*", lambda: T.glob_files("../*")), ("glob absolute", lambda: T.glob_files("/etc/*"))]:
        check(f"{label} is refused", raises(call) is not None and outside.read_text(encoding="utf-8") == "secret" and not (SANDBOX.parent / "evil.txt").exists())
    try:
        os.symlink(outside, SANDBOX / "link.txt")
        check("a symlink that points outside the sandbox is refused", "escapes" in (raises(T.read_file, "link.txt") or ""))
    except (OSError, NotImplementedError):
        print("[SKIP] symlink creation is not permitted on this system")

    # ------------------------------------------------------------------ the safety gate: the required 5 pass / 5 blocked
    print("\n### safety gate: SAFE_PREFIXES, confirm_bash, is_destructive")
    check("SAFE_PREFIXES is a module-level allow-list", isinstance(SAFE_PREFIXES, tuple) and "ls" in SAFE_PREFIXES and "git status" in SAFE_PREFIXES)
    must_pass = ["ls -la", "cat notes.txt", "grep -n DEBUG app.py", "git status", "echo hello"]
    must_block = ["rm -rf ./build", "sudo apt install foo", "chmod 777 app.py", "dd if=/dev/zero of=/dev/sda", "ls -la; rm -rf /"]
    for c in must_pass:
        d = confirm_bash(c)
        check(f"PASS  {c!r}: allowed ({d['reason']})", d["allowed"] is True and is_destructive(c) is False)
    for c in must_block:
        d = confirm_bash(c)
        check(f"BLOCK {c!r}: blocked ({d['reason'][:60]})", d["allowed"] is False and is_destructive(c) is True)

    # ------------------------------------------------------------------ the gate in depth: every category, evasions, false blocks
    print("\n### every destructive category, and ways of hiding one")
    destructive = {
        "recursive deletion": ["rm -rf /", "rm -fr build", "rm -r -f x", "rm --recursive dir", "rm -R x", "find . -name '*.tmp' -delete", "find . -exec rm -rf {} \\;",
                               "/bin/rm -rf x", "FOO=1 rm -rf x", "env rm -rf x", "nohup rm -rf x &", "timeout 5 rm -rf x", "xargs rm -rf < list.txt"],
        "privilege escalation": ["sudo ls", "su -", "doas reboot", "echo hi | sudo tee /tmp/x", "ls; sudo reboot", "pkexec bash"],
        "permission/ownership change": ["chmod 777 f", "chmod -R a+w .", "chown root f", "chgrp staff f", "setfacl -m u:x:rwx f"],
        "raw-device write": ["dd if=/dev/zero of=/dev/sda bs=1M", "dd if=x of=/dev/nvme0n1", "echo x > /dev/sda", "cat image.iso > /dev/sdb", "cp image /dev/sda"],
        "filesystem creation": ["mkfs.ext4 /dev/sdb1", "mkfs -t ext4 /dev/sdb1", "mkswap /dev/sdb2", "mke2fs /dev/sdc"],
        "redirection to a root path": ["echo x > /etc/passwd", "cat f >> /etc/hosts", "echo x >/etc/passwd", "ls > /", "echo x > /usr/bin/ls", "ls 2> /var/log/x"],
        "hidden behind shell keywords or computed names (found by probing, fixed)": ["{ rm -rf x; }", "if true; then rm -rf x; fi", "for i in 1 2; do rm -rf x; done", "! rm -rf x",
                                                                                      "while true; do sudo reboot; done", "echo hi && { sudo reboot; }", "$(echo rm) -rf x",
                                                                                      "echo x | tee /etc/passwd", "coproc rm -rf x"],
        "hidden inside another command": ["ls && rm -rf /", "ls || sudo reboot", "bash -c 'rm -rf /'", 'sh -c "sudo reboot"', 'eval "rm -rf /"', "echo $(rm -rf /)",
                                          "echo `rm -rf /`", "ls\nrm -rf /", 'echo "abc; rm -rf /', "(rm -rf /)", "cat a | xargs rm -rf"],
    }
    for category, commands in destructive.items():
        missed = [c for c in commands if not is_destructive(c)]
        check(f"{category}: all {len(commands)} variants are flagged destructive", not missed, f"MISSED: {missed}")
        leaked = [c for c in commands if confirm_bash(c)["allowed"]]
        check(f"{category}: none of them is allowed by confirm_bash", not leaked, f"ALLOWED: {leaked}")
    benign = ['echo "rm -rf /"', "grep -r sudo .", "echo chmod 777", "ls -la", "cat notes.txt", "echo hi > out.txt", "rm file.txt", "cat a 2>&1", "git log --oneline",
              'grep -n "mkfs" notes.txt', 'echo "a > /etc/passwd"', "ls | wc -l", "cat a 2>/dev/null", 'echo "{ rm -rf x; }"', "echo if then fi", "echo $(date)", "echo done"]
    wrongly = [c for c in benign if is_destructive(c)]
    check(f"{len(benign)} harmless commands that only MENTION dangerous words are not flagged (no false blocks)", not wrongly, f"FLAGGED: {wrongly}")

    print("\n### confirm_bash decisions")
    check("safe prefixes pass, including a pipe between safe commands", confirm_bash("ls | wc -l")["allowed"] and confirm_bash("git diff")["allowed"])
    check("a safe-looking command with chaining or a redirect is NOT auto-allowed", not confirm_bash("ls; echo x")["allowed"] and not confirm_bash("echo hi > out.txt")["allowed"]
          and not confirm_bash("echo $(date)")["allowed"])
    check("a command that is not in SAFE_PREFIXES is blocked by default", confirm_bash("python script.py") == {"allowed": False, "reason": "blocked: not in SAFE_PREFIXES and not approved"})
    check("auto_approve=True allows a non-destructive command outside SAFE_PREFIXES", confirm_bash("python script.py", auto_approve=True)["allowed"])
    check("auto_approve=True does NOT allow a destructive command", not confirm_bash("rm -rf x", auto_approve=True)["allowed"] and not confirm_bash("ls; rm -rf /", auto_approve=True)["allowed"])
    check("a destructive command is allowed only with explicit confirmation (confirm returns True)", confirm_bash("rm -rf x", confirm=lambda c: True)["allowed"] is True)
    check("a refused confirmation keeps it blocked", not confirm_bash("rm -rf x", confirm=lambda c: False)["allowed"])
    check("only a real True counts as confirmation (a truthy string does not)", not confirm_bash("rm -rf x", confirm=lambda c: "yes")["allowed"])
    check("an empty command is blocked", not confirm_bash("   ")["allowed"])
    check("the block reason is short and says why", "recursive deletion" in confirm_bash("rm -rf x")["reason"] and len(confirm_bash("rm -rf x")["reason"]) < 120)
    check("destructive_reason names the category", destructive_reason("sudo ls") == "privilege escalation" and destructive_reason("mkfs.ext4 /dev/sdb") == "filesystem creation")

    # ------------------------------------------------------------------ bash tool: the gate really stands in front of execution
    print("\n### the bash tool runs only what the gate lets through")
    victim = SANDBOX / "victim_dir"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    msg = raises(T.bash, f"rm -rf {victim}")
    check("a blocked destructive command does not run: its target is still there", msg is not None and "safety gate" in msg and (victim / "keep.txt").exists(), str(msg))
    out = T.bash("echo hello")
    check("an allowed command runs inside the sandbox and returns its output", out["exit_code"] == 0 and out["stdout"].strip() == "hello" and out["gate"] == "matches SAFE_PREFIXES", str(out))
    check("a command outside SAFE_PREFIXES is refused when the model calls it (auto_approve is not available to the model)",
          "not in SAFE_PREFIXES" in (raises(T.bash, "python -c 1") or ""))
    check("the tool schema offers the model only a 'command' argument", list(TOOL_SPECS["bash"]["parameters"]["properties"]) == ["command"])

    # ------------------------------------------------------------------ integration through the Part 2 agent loop (scripted model)
    print("\n### glob -> search -> read through the agent loop (scripted model, real tools)")
    work = make_sandbox()
    try:
        W = FileTools(work)
        W.write_file("alpha.py", "def add(a, b):\n    return a + b\n")
        W.write_file("beta.py", "DEBUG = True\n\ndef log(msg):\n    if DEBUG:\n        print(msg)\n")
        W.write_file("gamma.py", "NAME = 'gamma'\n")

        class Scripted:
            def __init__(self, replies):
                self.replies = list(replies)

            def chat(self, messages, tools=None):
                r = self.replies.pop(0)
                return {"content": r.get("content", ""), "tool_calls": r.get("tool_calls", []), "invalid_tool_calls": [], "usage": {"input_tokens": 10, "output_tokens": 5},
                        "latency_ms": 1.0}

        def call(name, args, i):
            return {"tool_calls": [{"name": name, "args": args, "id": f"c{i}"}]}

        beta_text = (work / "beta.py").read_text(encoding="utf-8")
        run = run_agent("Find the Python file that contains DEBUG and show its contents.",
                        model=Scripted([call("glob_files", {"pattern": "*.py"}, 1), call("search_in_files", {"pattern": "DEBUG", "file_pattern": "*.py"}, 2),
                                        call("read_file", {"path": "beta.py"}, 3), {"content": "The file is beta.py:\n" + beta_text}]),
                        tool_specs=TOOL_SPECS, executor=make_executor(W), log_path=work / "log.jsonl")
        order = [t["tool"] for t in run["trace"]]
        check("the loop called glob_files, then search_in_files, then read_file, in that order", order == ["glob_files", "search_in_files", "read_file"], str(order))
        check("the search result named beta.py and the read returned its real contents", "beta.py" in run["messages"][-4]["content"] and "DEBUG = True" in run["messages"][-2]["content"])
        check("the final answer shows the file's contents and the run stopped normally", run["stop_reason"] == "final_answer" and "DEBUG = True" in run["final_answer"])
        bad = run_agent("clean up", model=Scripted([call("bash", {"command": f"rm -rf {work}"}, 1), {"content": "done"}]), tool_specs=TOOL_SPECS, executor=make_executor(W),
                        log_path=work / "log2.jsonl")
        obs = json.loads(bad["messages"][-2]["content"])
        check("a model that asks bash to delete the sandbox is stopped by the gate (error returned to the model, files still there)",
              obs["ok"] is False and "safety gate" in obs["error"] and (work / "beta.py").exists(), str(obs))
        sneaky = run_agent("x", model=Scripted([call("bash", {"command": "echo hi", "auto_approve": True}, 1), {"content": "done"}]), tool_specs=TOOL_SPECS, executor=make_executor(W),
                           log_path=work / "log3.jsonl")
        check("a model that tries to pass auto_approve itself is rejected by the strict tool schema before anything runs", sneaky["tool_calls_invalid"] == 1 and sneaky["tool_calls_executed"] == 0)
    finally:
        shutil.rmtree(work, ignore_errors=True)
finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)
    for stray in (SANDBOX.parent / "outside_secret.txt",):
        stray.unlink(missing_ok=True)

check("the temporary sandbox was deleted at the end", not SANDBOX.exists())
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
for n in failed:
    print("FAILED:", n)
sys.exit(1 if failed else 0)
