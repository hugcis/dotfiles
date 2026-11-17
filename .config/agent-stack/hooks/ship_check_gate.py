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
import subprocess
import sys
from pathlib import Path

GUARDED_TOOLS = {"file_system.bash", "process_start"}
GUARDED_RE = re.compile(r"(^|[;&|()]|\s)(git\s+push\b|gh\s+pr\s+(create|ready)\b)")


def allow(message: str = "ship-check gate: not a guarded command") -> dict:
    return {"decision": "allow", "message": message}


def deny(message: str) -> dict:
    return {"decision": "deny", "message": message}


def git_out(cwd: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


def repo_id(cwd: str) -> str:
    root = Path(git_out(cwd, "rev-parse", "--show-toplevel")).resolve()
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return f"{root.name}-{digest}"


def receipt_file(cwd: str, sha: str) -> Path:
    return Path.home() / ".local" / "state" / "ship-check" / repo_id(cwd) / f"{sha}.json"


def command_from(payload: dict) -> tuple[str | None, str]:
    tool = payload.get("tool_name") or payload.get("name") or ""
    if tool not in GUARDED_TOOLS:
        return None, ""
    tool_input = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if not isinstance(tool_input, dict):
        return None, ""
    command = tool_input.get("command") or tool_input.get("cmd")
    cwd = tool_input.get("cwd") or tool_input.get("directory") or os.getcwd()
    return (command if isinstance(command, str) else None), str(cwd)


def decision(payload: dict) -> dict:
    command, cwd = command_from(payload)
    if not command or not GUARDED_RE.search(command):
        return allow()
    try:
        sha = git_out(cwd, "rev-parse", "HEAD")
        tree_hash = git_out(cwd, "rev-parse", "HEAD^{tree}")
        path = receipt_file(cwd, sha)
        if not path.exists():
            return deny(f"ship-check receipt missing for current HEAD {sha}; run ship-check first")
        receipt = json.loads(path.read_text())
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        return deny(f"ship-check gate could not verify receipt: {error}")
    if receipt.get("overall") != "pass":
        return deny(f"ship-check receipt is not passing for {sha}")
    if receipt.get("sha") != sha or receipt.get("tree_hash") != tree_hash:
        return deny("ship-check receipt does not match current HEAD sha and tree hash")
    return allow(f"ship-check receipt verified for {sha}")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = decision(payload if isinstance(payload, dict) else {})
    except Exception as error:  # hooks fail closed
        result = deny(f"ship-check gate failed closed: {error}")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
