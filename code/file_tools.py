"""
DATA-260 Homework 7 - Part 6: six file tools and a safety gate for the bash tool.

  read_file(path, max_lines)            glob_files(pattern)
  write_file(path, content)             search_in_files(pattern, file_pattern)
  edit_file(path, old_string, new_string) -> short diff        bash(command)  (every command goes through confirm_bash first)

Every path is resolved inside ONE sandbox directory (a temporary "course sandbox" in the tests); a path that escapes it (.., an absolute path,
a symlink out) is refused. The safety gate is pure Python, so it is testable without a model:

  SAFE_PREFIXES              commands that may run without asking
  is_destructive(command)    an INDEPENDENT deny-list: recursive deletion, privilege escalation, permission/ownership changes, raw-device
                             writes, filesystem creation, redirection to root paths. It looks inside chained commands, bash -c, eval,
                             $(...) / backticks, wrappers such as env/xargs/nohup, and find -exec/-delete.
  confirm_bash(command, auto_approve=False, confirm=None)  -> {"allowed": bool, "reason": str}
        destructive  -> blocked unless `confirm(command)` returns True (explicit confirmation); auto_approve does NOT apply, and a
                        SAFE_PREFIXES match does not help
        safe prefix  -> allowed
        anything else-> allowed only with auto_approve=True or confirm(command) returning True
The model is never given auto_approve or confirm: the tool schema for bash has a single `command` field.
"""

import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_RESULTS = 100
MAX_FILE_BYTES = 1_000_000
MAX_OUTPUT_CHARS = 4000

# --------------------------------------------------------------------------- the safety gate
SAFE_PREFIXES = ("ls", "pwd", "cat", "head", "tail", "wc", "echo", "grep", "which", "whoami", "date",
                 "git status", "git diff", "git log", "python --version", "python3 --version")

_SEPARATORS = set(";|&()")            # operator tokens made only of these characters separate commands
_WRAPPERS = {"env", "nohup", "nice", "time", "command", "builtin", "exec", "stdbuf", "timeout", "xargs", "setsid", "ionice"}
_PRIVILEGE = {"sudo", "su", "doas", "pkexec", "runas", "run0"}
_PERMISSION = {"chmod", "chown", "chgrp", "setfacl", "chattr", "icacls", "takeown"}
_FS_CREATE = {"mke2fs", "mkswap", "newfs", "mkntfs", "mkdosfs", "mkfs"}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash"}
_DEVICE = re.compile(r"^/dev/(sd|hd|vd|xvd|nvme|mmcblk|loop|disk|mapper|dm-|md|sr|fd|ram|mem|kmem|port)", re.I)
_ROOT_PATH = re.compile(r"^/(etc|bin|sbin|usr|lib|lib32|lib64|boot|proc|sys|root|var|opt|srv|home|mnt|media)(/|$)")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# shell keywords that can sit in front of the real command word: `{ rm -rf x; }`, `if c; then rm -rf x; fi`, `for i in 1; do rm -rf x; done`, `! rm -rf x`
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "case", "esac", "in", "select", "function", "coproc"}
_OK_DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/zero", "/dev/urandom"}


def _tokens(command: str) -> list[str]:
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def _is_operator(tok: str) -> bool:
    return bool(tok) and set(tok) <= set(";|&()<>0123456789") and any(c in tok for c in ";|&()<>") and not tok.isdigit()


def _redirect_reason(target: str) -> str | None:
    if target in _OK_DEVICES:
        return None
    if _DEVICE.match(target):
        return "raw-device write (redirection to a device)"
    if target == "/" or _ROOT_PATH.match(target):
        return "redirection to a root path"
    return None


def _words_reason(words: list[str]) -> str | None:
    """Why this single command (already split from any chain, redirections removed) is destructive, or None."""
    words = list(words)
    while words and (_ASSIGN.match(words[0]) or words[0] in _KEYWORDS):
        words.pop(0)
    while words and os.path.basename(words[0]) in _WRAPPERS:
        wrapper = os.path.basename(words.pop(0))
        while words and (words[0].startswith("-") or (wrapper in ("timeout", "nice", "ionice") and re.fullmatch(r"[\d.]+[smhd]?", words[0]))
                         or _ASSIGN.match(words[0])):
            words.pop(0)
    if not words:
        return None
    cmd, args = os.path.basename(words[0]), words[1:]
    if words[0].startswith(("$", "`")):
        return "computed command name (cannot be checked)"
    if cmd in _PRIVILEGE:
        return "privilege escalation"
    if cmd in _PERMISSION:
        return "permission/ownership change"
    if cmd.startswith("mkfs") or cmd in _FS_CREATE:
        return "filesystem creation"
    if cmd == "rm":
        flags = [a for a in args if a.startswith("-")]
        if any(f in ("--recursive", "--no-preserve-root") or (not f.startswith("--") and ("r" in f or "R" in f)) for f in flags):
            return "recursive deletion"
    if cmd == "find":
        if "-delete" in args:
            return "recursive deletion (find -delete)"
        for flag in ("-exec", "-execdir", "-ok", "-okdir"):
            if flag in args:
                inner = _words_reason(args[args.index(flag) + 1:])
                if inner:
                    return inner
    if cmd == "dd" and any(a.startswith("of=") and _DEVICE.match(a[3:]) for a in args):
        return "raw-device write"
    if cmd in ("cp", "mv", "tee") and any(_DEVICE.match(a) for a in args):
        return "raw-device write"
    if cmd == "tee" and any(a == "/" or _ROOT_PATH.match(a) for a in args):
        return "write to a root path (tee)"
    if cmd in _SHELLS and "-c" in args and args.index("-c") + 1 < len(args):
        return destructive_reason(args[args.index("-c") + 1])
    if cmd == "eval":
        return destructive_reason(" ".join(args))
    return None


def destructive_reason(command: str) -> str | None:
    """None if the command looks non-destructive, else a short reason. Fails closed: a command that cannot be parsed counts as destructive."""
    for inner in re.findall(r"\$\(([^()]*)\)", command) + re.findall(r"`([^`]*)`", command):
        reason = destructive_reason(inner)
        if reason:
            return reason
    try:
        tokens = _tokens(command)
    except ValueError:
        return "could not be parsed (unbalanced quotes), treated as destructive"
    segment: list[str] = []
    segments: list[list[str]] = []
    reason = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _is_operator(tok) and any(c in tok for c in "<>"):          # a redirection: check where it writes, skip its target
            if ">" in tok and i + 1 < len(tokens) and not re.fullmatch(r"\d+|-", tokens[i + 1]):
                reason = reason or _redirect_reason(tokens[i + 1])
            i += 2
            continue
        if _is_operator(tok):
            segments.append(segment)
            segment = []
        else:
            segment.append(tok)
        i += 1
    segments.append(segment)
    if reason:
        return reason
    for words in segments:
        reason = _words_reason(words)
        if reason:
            return reason
    return None


def is_destructive(command: str) -> bool:
    return destructive_reason(command) is not None


def _matches_safe_prefix(words: list[str]) -> bool:
    return any(words[: len(p.split())] == p.split() for p in SAFE_PREFIXES)


def _is_safe_prefix_command(command: str) -> bool:
    """Only plain commands, optionally piped into each other, each starting with a SAFE_PREFIXES entry. Anything with a redirection,
    chaining (; && || &), a subshell or a substitution is not 'safe' (it may still be allowed with approval)."""
    if "$(" in command or "`" in command:
        return False
    try:
        tokens = _tokens(command)
    except ValueError:
        return False
    segment: list[str] = []
    for tok in tokens + ["|"]:
        if tok == "|":
            if not segment or not _matches_safe_prefix(segment):
                return False
            segment = []
        elif _is_operator(tok):
            return False
        else:
            segment.append(tok)
    return True


def confirm_bash(command: str, auto_approve: bool = False, confirm=None) -> dict:
    """Decide whether `command` may run. Returns {"allowed": bool, "reason": str}. `confirm` is an optional callable(command) -> bool standing
    for the human's explicit answer; it is the only thing that can allow a destructive command."""
    cmd = (command or "").strip()
    if not cmd:
        return {"allowed": False, "reason": "empty command"}
    why = destructive_reason(cmd)
    if why:
        if confirm is not None and confirm(cmd) is True:
            return {"allowed": True, "reason": f"destructive ({why}) but explicitly confirmed"}
        return {"allowed": False, "reason": f"blocked: destructive ({why}); needs explicit confirmation (auto_approve does not apply)"}
    if _is_safe_prefix_command(cmd):
        return {"allowed": True, "reason": "matches SAFE_PREFIXES"}
    if auto_approve or (confirm is not None and confirm(cmd) is True):
        return {"allowed": True, "reason": "not in SAFE_PREFIXES, approved"}
    return {"allowed": False, "reason": "blocked: not in SAFE_PREFIXES and not approved"}


# --------------------------------------------------------------------------- the six tools
class ToolError(Exception):
    """A normal, reportable failure (bad path, no match, ...). The agent loop turns it into {ok: false, error}."""


def make_sandbox() -> Path:
    return Path(tempfile.mkdtemp(prefix="data260_sandbox_"))


class FileTools:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ToolError("path is empty")
        p = (self.root / path).resolve()
        if p != self.root and self.root not in p.parents:
            raise ToolError(f"path escapes the sandbox: {path}")
        return p

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def read_file(self, path: str, max_lines: int | None = None) -> dict:
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"no such file: {path}")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        shown = lines if max_lines is None else lines[: max(int(max_lines), 0)]
        return {"path": self._rel(p), "content": "\n".join(shown), "lines_returned": len(shown), "total_lines": len(lines), "truncated": len(shown) < len(lines)}

    def write_file(self, path: str, content: str) -> dict:
        p = self._resolve(path)
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        return {"path": self._rel(p), "bytes": len(content.encode("utf-8")), "created": not existed}

    def edit_file(self, path: str, old_string: str, new_string: str) -> dict:
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"no such file: {path}")
        if not old_string:
            raise ToolError("old_string is empty")
        before = p.read_text(encoding="utf-8")
        count = before.count(old_string)
        if count == 0:
            raise ToolError("old_string was not found")
        if count > 1:
            raise ToolError(f"old_string appears {count} times; give more context so it matches exactly once")
        after = before.replace(old_string, new_string, 1)
        p.write_text(after, encoding="utf-8", newline="\n")
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{self._rel(p)}", f"b/{self._rel(p)}", n=1, lineterm=""))
        return {"path": self._rel(p), "replacements": 1, "diff": "\n".join(diff[:40]) + ("\n..." if len(diff) > 40 else "")}

    def glob_files(self, pattern: str) -> dict:
        if not pattern or pattern.startswith(("/", "\\")) or ".." in Path(pattern).parts:
            raise ToolError("pattern must be relative to the sandbox and must not contain ..")
        found = sorted(self._rel(p) for p in self.root.glob(pattern) if p.is_file() and self.root in p.resolve().parents)
        return {"pattern": pattern, "files": found[:MAX_RESULTS], "count": len(found), "truncated": len(found) > MAX_RESULTS}

    def search_in_files(self, pattern: str, file_pattern: str = "*") -> dict:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"invalid regular expression: {e}")
        matches, files_searched = [], 0
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or self.root not in p.resolve().parents or not (p.match(file_pattern) or Path(self._rel(p)).match(file_pattern)):
                continue
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue                                    # binary file
            files_searched += 1
            for n, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    matches.append({"file": self._rel(p), "line": n, "text": line.strip()[:200]})
        return {"pattern": pattern, "file_pattern": file_pattern, "files_searched": files_searched, "matches": matches[:MAX_RESULTS],
                "count": len(matches), "truncated": len(matches) > MAX_RESULTS}

    def bash(self, command: str, auto_approve: bool = False, confirm=None, timeout: int = 10) -> dict:
        gate = confirm_bash(command, auto_approve=auto_approve, confirm=confirm)
        if not gate["allowed"]:
            raise ToolError(f"safety gate: {gate['reason']}")
        argv = ["bash", "-c", command] if shutil.which("bash") else command
        try:
            done = subprocess.run(argv, shell=isinstance(argv, str), cwd=self.root, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(f"command timed out after {timeout} s")
        return {"command": command, "gate": gate["reason"], "exit_code": done.returncode,
                "stdout": done.stdout[:MAX_OUTPUT_CHARS], "stderr": done.stderr[:MAX_OUTPUT_CHARS]}


# --------------------------------------------------------------------------- what the model is told, and the executor for the Part 2 agent loop
TOOL_SPECS = {
    "read_file": {"description": "Read a text file inside the sandbox. max_lines limits how many lines are returned (total_lines and truncated are reported).",
                  "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "max_lines": {"type": "integer", "minimum": 1}},
                                 "required": ["path"], "additionalProperties": False}},
    "write_file": {"description": "Create or overwrite a text file inside the sandbox.",
                   "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                                  "required": ["path", "content"], "additionalProperties": False}},
    "edit_file": {"description": "Replace one exact occurrence of old_string with new_string in a file; returns a short diff.",
                  "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}},
                                 "required": ["path", "old_string", "new_string"], "additionalProperties": False}},
    "glob_files": {"description": "List files in the sandbox matching a glob pattern such as '*.py' or '**/*.txt'.",
                   "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"], "additionalProperties": False}},
    "search_in_files": {"description": "Search file contents with a regular expression. file_pattern (default '*') limits which files are searched, e.g. '*.py'. "
                                       "Returns file, line number and the matching line.",
                        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "file_pattern": {"type": "string"}},
                                       "required": ["pattern"], "additionalProperties": False}},
    "bash": {"description": "Run a shell command in the sandbox. Every command goes through a safety gate; destructive or unlisted commands are refused.",
             "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}},
}


def make_executor(tools: FileTools):
    """callable(name, args) -> JSON string {ok, data, error}, the shape the Part 2 agent loop expects. The model cannot pass auto_approve or confirm."""
    def executor(name: str, args: dict) -> str:
        try:
            data = getattr(tools, name)(**args)
            return json.dumps({"ok": True, "data": data, "error": None})
        except ToolError as e:
            return json.dumps({"ok": False, "data": None, "error": str(e)})
    return executor
