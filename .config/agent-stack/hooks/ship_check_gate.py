#!/usr/bin/env python3
"""Inline ship gate: rerun deterministic checks and require CI for ready/merge."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ship_check_core import deterministic_checks, failed_checks, git_out

SEGMENT_OPERATORS = {";", "&&", "||", "|", "\n", "(", ")", "{", "}"}
WRAPPER_COMMANDS = {"command", "exec", "sudo", "doas", "nohup"}
OPTION_WRAPPERS = {"timeout", "nice", "stdbuf"}
STDBUF_OPTIONS_WITH_VALUE = {"-i", "-o", "-e", "--input", "--output", "--error"}
SHELL_COMMANDS = {"bash", "sh", "zsh"}
MAX_SHELL_RECURSION = 2
GIT_GLOBAL_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree"}
GH_GUARDED = {("pr", "create"), ("pr", "ready"), ("pr", "merge")}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*")
UNREADABLE_PATTERNS = (
    re.compile(r"\|\s*(bash|sh|zsh)\b"),
    re.compile(r"\b(bash|sh|zsh)\b.*<<<"),
    re.compile(r"<<\s*\w+.*\|\s*(bash|sh|zsh)\b", re.S),
    re.compile(r"\bxargs\b"),
    re.compile(r"\bssh\b.*\bgit\s+push\b"),
)


@dataclass
class Guarded:
    kind: str
    repo: Path | None
    reason: str | None = None


def allow() -> dict | None:
    return None


def deny(reason: str) -> dict:
    return {"decision": "deny", "reason": reason}


def command_from(payload: dict) -> tuple[str | None, Path]:
    tool_input = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if not isinstance(tool_input, dict):
        return None, Path(str(payload.get("cwd") or os.getcwd()))
    command = tool_input.get("command") or tool_input.get("cmd")
    cwd = payload.get("cwd") or tool_input.get("cwd") or tool_input.get("directory") or os.getcwd()
    return (command if isinstance(command, str) else None), Path(str(cwd))


def shell_words(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n(){}")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    return list(lexer)


def command_segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for word in shell_words(command):
        if word in SEGMENT_OPERATORS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(word)
    if current:
        segments.append(current)
    return segments


def basename(word: str) -> str:
    return Path(word).name


def strip_prefixes(words: list[str]) -> list[str]:
    words = list(words)
    while words:
        head = basename(words[0])
        if head in WRAPPER_COMMANDS:
            words.pop(0)
            continue
        if head == "env":
            words.pop(0)
            while words and ASSIGNMENT.match(words[0]):
                words.pop(0)
            continue
        if head == "timeout":
            words.pop(0)
            while words and words[0].startswith("-"):
                words.pop(0)
            if words:
                words.pop(0)
            continue
        if head == "nice":
            words.pop(0)
            if len(words) >= 2 and words[0] == "-n":
                words.pop(0)
                words.pop(0)
            continue
        if head == "stdbuf":
            words.pop(0)
            while words:
                option = words[0]
                if not option.startswith("-"):
                    break
                words.pop(0)
                if option in STDBUF_OPTIONS_WITH_VALUE and words:
                    words.pop(0)
            continue
        if ASSIGNMENT.match(words[0]):
            words.pop(0)
            continue
        break
    return words


def resolve_path(cwd: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


def parse_git(words: list[str], cwd: Path) -> Guarded | None:
    words = strip_prefixes(words)
    if not words or basename(words.pop(0)) != "git":
        return None
    repo = cwd
    git_dir = None
    work_tree = None
    while words:
        word = words.pop(0)
        value = None
        if word == "--":
            continue
        if word in GIT_GLOBAL_OPTIONS_WITH_VALUE:
            value = words.pop(0) if words else ""
        else:
            for option in GIT_GLOBAL_OPTIONS_WITH_VALUE:
                if word.startswith(option + "="):
                    value = word.split("=", 1)[1]
                    word = option
                    break
        if value is not None:
            if word == "-C":
                repo = resolve_path(repo, value)
            elif word == "--work-tree":
                work_tree = resolve_path(cwd, value)
            elif word == "--git-dir":
                git_dir = resolve_path(cwd, value)
            continue
        if word.startswith("-"):
            continue
        if word == "push":
            if work_tree:
                return Guarded("push", work_tree)
            if git_dir and not work_tree:
                return Guarded("push", None, "cannot resolve push target from --git-dir alone; run the push from inside the repo")
            return Guarded("push", repo)
        return None
    return None


def parse_gh(words: list[str], cwd: Path) -> Guarded | None:
    words = strip_prefixes(words)
    if len(words) < 3 or basename(words[0]) != "gh":
        return None
    pair = (words[1], words[2])
    if pair in GH_GUARDED:
        return Guarded("gh_" + pair[1], cwd)
    return None


def nested_command(words: list[str]) -> str | None:
    words = strip_prefixes(words)
    if not words:
        return None
    head = basename(words[0])
    if head == "eval" and len(words) >= 2:
        return " ".join(words[1:])
    if head not in SHELL_COMMANDS:
        return None
    index = 1
    while index < len(words):
        word = words[index]
        if word == "-c":
            return words[index + 1] if index + 1 < len(words) else ""
        if word.startswith("-"):
            index += 1
            continue
        return None
    return None


def guarded_segment(words: list[str], cwd: Path, depth: int) -> Guarded | None:
    if not words:
        return None
    if basename(words[0]) == "cd" and len(words) >= 2:
        return Guarded("cd", resolve_path(cwd, words[1]))
    for parser in (parse_git, parse_gh):
        found = parser(list(words), cwd)
        if found:
            return found
    inner = nested_command(list(words))
    if inner is None:
        return None
    if depth >= MAX_SHELL_RECURSION:
        return Guarded("unreadable", None, "nested shell command is too deep; run the push from inside the repo")
    if not inner:
        return Guarded("unreadable", None, "nested shell command is empty or unparseable; run the push from inside the repo")
    return first_guarded(inner, cwd, depth + 1)


def first_guarded(command: str, cwd: Path, depth: int = 0) -> Guarded | None:
    if any(pattern.search(command) for pattern in UNREADABLE_PATTERNS):
        return Guarded("unreadable", None, "unreadable shell-fed or remote push; run the push from inside the repo")
    current_cwd = cwd
    for segment in command_segments(command):
        found = guarded_segment(segment, current_cwd, depth)
        if not found:
            continue
        if found.kind == "cd" and found.repo:
            current_cwd = found.repo
            continue
        return found
    return None


def inline_reason(repo: Path) -> str | None:
    try:
        checks = deterministic_checks(repo)
    except subprocess.CalledProcessError:
        return f"ship-check could not identify refs in {repo}; run the push from inside the repo"
    failures = failed_checks(checks)
    if failures:
        return "; ".join(f"{check['name']}: {check['summary']}" for check in failures)
    return None


def check_ci(repo: Path) -> str | None:
    try:
        head = git_out(repo, "rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        return f"ship-check could not identify a git repository at {repo}; run the push from inside the repo"
    proc = subprocess.run(
        ["gh", "pr", "view", "--json", "headRefOid,statusCheckRollup"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return f"gh pr view --json headRefOid,statusCheckRollup failed; ensure gh is authenticated and run from the PR repo: {(proc.stderr or proc.stdout).strip()}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        return f"gh pr view returned invalid JSON: {error}"
    if data.get("headRefOid") != head:
        return f"PR head {data.get('headRefOid')} does not match current HEAD {head}"
    checks = data.get("statusCheckRollup") or []
    if not checks:
        return f"no status checks found for PR head {head}; wait for required CI before ready/merge"
    bad = []
    for check in checks:
        conclusion = str(check.get("conclusion") or check.get("status") or "").upper()
        if conclusion not in {"SUCCESS", "COMPLETED"}:
            bad.append(check.get("name") or check.get("context") or json.dumps(check, sort_keys=True))
    if bad:
        return f"status checks are not all SUCCESS for PR head {head}: {', '.join(map(str, bad))}"
    return None


def decision(payload: dict) -> dict | None:
    command, cwd = command_from(payload)
    if not command:
        return allow()
    try:
        guarded = first_guarded(command, cwd)
    except ValueError:
        return deny("command could not be parsed; run the push from inside the repo")
    if not guarded:
        return allow()
    if guarded.reason:
        return deny(guarded.reason)
    if not guarded.repo:
        return deny("cannot resolve push target; run the push from inside the repo")
    reason = inline_reason(guarded.repo)
    if reason:
        return deny(reason)
    if guarded.kind in {"gh_ready", "gh_merge"}:
        ci_reason = check_ci(guarded.repo)
        if ci_reason:
            return deny(ci_reason)
    return allow()


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = decision(payload if isinstance(payload, dict) else {})
    except Exception as error:
        result = deny(f"ship-check gate failed closed: {error}")
    if result is not None:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
