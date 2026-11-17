#!/usr/bin/env python3
"""Deny push/PR publication unless ship-check wrote a passing receipt for HEAD.

L1 policy requirement: agents must be denied direct write/edit access under
~/.local/state/ship-check/**. The ship-check CLI is the only allowed writer;
this hook only reads receipts and verifies the current sha and tree hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

SEGMENT_OPERATORS = {";", "&&", "||", "|", "\n"}
WRAPPER_COMMANDS = {"command", "exec"}
SHELL_COMMANDS = {"bash", "sh", "zsh"}
MAX_SHELL_RECURSION = 2
GIT_GLOBAL_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree"}
GIT_GUARDED_SUBCOMMANDS = {"push"}
GH_GUARDED = {("pr", "create"), ("pr", "ready"), ("pr", "merge")}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*")


def allow() -> dict | None:
    return None


def deny(reason: str) -> dict:
    return {"decision": "deny", "reason": reason}


def git_out(cwd: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


def repo_id(cwd: str) -> str:
    root = Path(git_out(cwd, "rev-parse", "--show-toplevel")).resolve()
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return f"{root.name}-{digest}"


def receipt_file(cwd: str, sha: str) -> Path:
    return Path.home() / ".local" / "state" / "ship-check" / repo_id(cwd) / f"{sha}.json"


def command_from(payload: dict) -> tuple[str | None, str]:
    tool_input = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if not isinstance(tool_input, dict):
        return None, str(payload.get("cwd") or os.getcwd())
    command = tool_input.get("command") or tool_input.get("cmd")
    cwd = payload.get("cwd") or tool_input.get("cwd") or tool_input.get("directory") or os.getcwd()
    return (command if isinstance(command, str) else None), str(cwd)


def shell_words(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
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
        if ASSIGNMENT.match(words[0]):
            words.pop(0)
            continue
        break
    return words


def git_subcommand(words: list[str]) -> str | None:
    words = strip_prefixes(words)
    if not words or basename(words.pop(0)) != "git":
        return None
    while words:
        word = words.pop(0)
        if word == "--":
            continue
        if word in GIT_GLOBAL_OPTIONS_WITH_VALUE:
            if words:
                words.pop(0)
            continue
        if any(word.startswith(option + "=") for option in GIT_GLOBAL_OPTIONS_WITH_VALUE):
            continue
        if word.startswith("-"):
            continue
        return word
    return None


def gh_command(words: list[str]) -> tuple[str, str] | None:
    words = strip_prefixes(words)
    if len(words) < 3 or basename(words[0]) != "gh":
        return None
    return words[1], words[2]


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


def is_guarded_segment(words: list[str], depth: int) -> tuple[bool, str | None]:
    if git_subcommand(list(words)) in GIT_GUARDED_SUBCOMMANDS:
        return True, None
    gh = gh_command(list(words))
    if gh in GH_GUARDED:
        return True, None
    inner = nested_command(list(words))
    if inner is None:
        return False, None
    if depth >= MAX_SHELL_RECURSION:
        return True, "nested shell command is too deep; run ship-check in the repo first"
    if not inner:
        return True, "nested shell command is empty or unparseable; run ship-check in the repo first"
    try:
        return is_guarded_command(inner, depth + 1)
    except ValueError:
        return True, "nested shell command could not be parsed; run ship-check in the repo first"


def is_guarded_command(command: str, depth: int = 0) -> tuple[bool, str | None]:
    guarded = False
    for segment in command_segments(command):
        segment_guarded, reason = is_guarded_segment(segment, depth)
        if reason:
            return True, reason
        guarded = guarded or segment_guarded
    return guarded, None


def decision(payload: dict) -> dict | None:
    command, cwd = command_from(payload)
    if not command:
        return allow()
    try:
        guarded, parse_reason = is_guarded_command(command)
    except ValueError:
        guarded, parse_reason = True, "command could not be parsed; run ship-check in the repo first"
    if not guarded:
        return allow()
    if parse_reason:
        return deny(parse_reason)
    try:
        sha = git_out(cwd, "rev-parse", "HEAD")
        tree_hash = git_out(cwd, "rev-parse", "HEAD^{tree}")
        path = receipt_file(cwd, sha)
        if not path.exists():
            return deny(f"ship-check receipt missing for current HEAD {sha}; run ship-check in {cwd} first")
        receipt = json.loads(path.read_text())
    except subprocess.CalledProcessError:
        return deny(f"ship-check could not identify a git repository at {cwd}; run ship-check in {cwd} first")
    except (OSError, json.JSONDecodeError) as error:
        return deny(f"ship-check gate could not verify receipt; run ship-check in {cwd} first: {error}")
    if receipt.get("overall") != "pass":
        return deny(f"ship-check receipt is not passing for {sha}")
    if receipt.get("sha") != sha or receipt.get("tree_hash") != tree_hash:
        return deny("ship-check receipt does not match current HEAD sha and tree hash")
    return allow()


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = decision(payload if isinstance(payload, dict) else {})
    except Exception as error:  # hooks fail closed
        result = deny(f"ship-check gate failed closed: {error}")
    if result is not None:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
