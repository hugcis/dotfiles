#!/usr/bin/env python3
"""Inline ship gate: rerun checks, require CI, and catch risky publication commands.

This is a guardrail against mistakes; GitHub branch protection is the enforcement boundary.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from ship_check_core import deterministic_checks, failed_checks, git_out

SEGMENT_OPERATORS = {";", "&&", "||", "|", "\n", "(", ")", "{", "}"}
WRAPPER_COMMANDS = {"command", "exec", "sudo", "doas", "nohup"}
OPTION_WRAPPERS = {"timeout", "nice", "stdbuf"}
STDBUF_OPTIONS_WITH_VALUE = {"-i", "-o", "-e", "--input", "--output", "--error"}
SHELL_COMMANDS = {"bash", "sh", "zsh"}
MAX_SHELL_RECURSION = 2
GIT_GLOBAL_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree"}
PUSH_OPTIONS_WITH_VALUE = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}
AMBIGUOUS_PUSH_FLAGS = {"--all", "--mirror", "--tags", "--follow-tags"}
GIT_MUTATING_SUBCOMMANDS = {"commit", "merge", "rebase", "cherry-pick", "am", "apply", "reset", "revert", "tag"}
GH_GUARDED = {("pr", "create"), ("pr", "ready"), ("pr", "merge")}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*")
UNREADABLE_PATTERNS = (
    re.compile(r"\|\s*(bash|sh|zsh)\b"),
    re.compile(r"\b(bash|sh|zsh)\b.*<<<"),
    re.compile(r"<<\s*\w+.*\|\s*(bash|sh|zsh)\b", re.S),
    re.compile(r"\bxargs\b.*\b(git|gh)\b"),
    re.compile(r"\bgit\s+push\b.*\|\s*xargs\b|\|\s*xargs\b.*\bgit\s+push\b"),
    re.compile(r"\bssh\b.*\bgit\s+push\b"),
)


@dataclass
class Guarded:
    kind: str
    repo: Path | None
    reason: str | None = None
    heads: list[str] = field(default_factory=list)
    pr: str | None = None
    gh_repo: str | None = None
    gh_host: str | None = None


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


def normalize_token(word: str) -> str:
    return word.strip("(){}")


def command_segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for raw in shell_words(command):
        word = normalize_token(raw)
        if not word:
            if current:
                segments.append(current)
                current = []
            continue
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


def split_git_global_options(words: list[str], cwd: Path) -> tuple[Path, list[str], str | None]:
    words = list(words)
    if not words or basename(words.pop(0)) != "git":
        return cwd, [], None
    repo = cwd
    git_dir = None
    work_tree = None
    rest: list[str] = []
    while words:
        word = words.pop(0)
        value = None
        if word == "--":
            rest.extend(words)
            break
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
        rest = [word, *words]
        break
    if work_tree:
        return work_tree, rest, None
    if git_dir and not work_tree:
        return repo, rest, "cannot resolve push target from --git-dir alone; run the push from inside the repo"
    return repo, rest, None


def push_refspecs(args: list[str]) -> tuple[list[str], str | None]:
    if any(token in AMBIGUOUS_PUSH_FLAGS for token in args):
        return [], "ambiguous git push mode; push explicit refspecs instead"
    operands: list[str] = []
    index = 0
    after_double_dash = False
    while index < len(args):
        token = args[index]
        if after_double_dash:
            operands.append(token)
            index += 1
            continue
        if token == "--":
            after_double_dash = True
            index += 1
            continue
        if token in PUSH_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if any(token.startswith(option + "=") for option in PUSH_OPTIONS_WITH_VALUE):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        operands.append(token)
        index += 1
    if any(token == "--repo" or token.startswith("--repo=") for token in args):
        return operands, None
    return (operands[1:] if len(operands) > 1 else ["HEAD"]), None


def resolve_push_source(repo: Path, refspec: str) -> tuple[str | None, str | None]:
    source = refspec.lstrip("+").split(":", 1)[0] or "HEAD"
    proc = subprocess.run(["git", "rev-parse", "--verify", source], cwd=repo, text=True, capture_output=True)
    if proc.returncode != 0:
        return None, f"unresolvable push source {source!r}; push explicit existing refs"
    return proc.stdout.strip(), None


def parse_git(words: list[str], cwd: Path) -> Guarded | None:
    words = strip_prefixes(words)
    if not words or basename(words[0]) != "git":
        return None
    repo, rest, repo_reason = split_git_global_options(words, cwd)
    if not rest:
        return None
    subcommand, args = rest[0], rest[1:]
    if subcommand == "push":
        if repo_reason:
            return Guarded("push", None, repo_reason)
        refspecs, reason = push_refspecs(args)
        if reason:
            return Guarded("push", repo, reason)
        heads = []
        for refspec in refspecs:
            head, error = resolve_push_source(repo, refspec)
            if error:
                return Guarded("push", repo, error)
            heads.append(head or "HEAD")
        return Guarded("push", repo, heads=heads or ["HEAD"])
    return None


def git_mutates_state(words: list[str], cwd: Path) -> bool:
    words = strip_prefixes(words)
    if not words or basename(words[0]) != "git":
        return False
    _repo, rest, _reason = split_git_global_options(words, cwd)
    if not rest:
        return False
    subcommand, args = rest[0], rest[1:]
    if subcommand in GIT_MUTATING_SUBCOMMANDS:
        return True
    if subcommand == "checkout" and any(arg == "-b" or arg.startswith("-b") for arg in args):
        return True
    if subcommand == "switch" and any(arg == "-c" or arg.startswith("-c") for arg in args):
        return True
    if subcommand == "stash" and args[:1] == ["pop"]:
        return True
    return False


def mutating_github_api(words: list[str]) -> bool:
    method = "GET"
    has_field = False
    path_parts = []
    graphql_mutation = False
    index = 0
    while index < len(words):
        token = words[index]
        if token in {"-X", "--method"} and index + 1 < len(words):
            method = words[index + 1].upper()
            index += 2
            continue
        if token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
        if token in {"-f", "-F", "--field", "--raw-field"}:
            has_field = True
            if index + 1 < len(words) and "mutation" in words[index + 1].lower():
                graphql_mutation = True
            index += 2
            continue
        if "mutation" in token.lower():
            graphql_mutation = True
        if not token.startswith("-"):
            path_parts.append(token)
        index += 1
    path = " ".join(path_parts)
    mutating = method in {"PATCH", "POST", "PUT", "DELETE"} or has_field or graphql_mutation
    sensitive = "pulls" in path or "pullRequest" in path or "merges" in path or graphql_mutation
    return mutating and sensitive


def parse_gh_api(words: list[str]) -> Guarded | None:
    if mutating_github_api(words):
        return Guarded("unreadable", None, "mutating GitHub PR API call blocked; this is a guardrail against mistakes; GitHub branch protection is the enforcement boundary")
    return None


def mutating_curl_or_wget(words: list[str]) -> bool:
    words = strip_prefixes(words)
    if not words or basename(words[0]) not in {"curl", "wget"}:
        return False
    method = "GET"
    url = ""
    index = 1
    while index < len(words):
        token = words[index]
        if token in {"-X", "--request", "--method"} and index + 1 < len(words):
            method = words[index + 1].upper()
            index += 2
            continue
        if token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
        if token.startswith("--method=") or token.startswith("--request="):
            method = token.split("=", 1)[1].upper()
        if token.startswith("http"):
            url = token
        index += 1
    return method in {"PATCH", "POST", "PUT", "DELETE"} and "api.github.com/repos/" in url and ("/pulls" in url or "/merges" in url)


def pr_url_identity(token: str) -> tuple[str | None, str | None]:
    parsed = urlparse(token)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        return None, None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 4 and parts[2] == "pull":
        return f"{parts[0]}/{parts[1]}", parts[3]
    return None, None


def parse_gh(words: list[str], cwd: Path) -> Guarded | None:
    gh_repo = None
    gh_host = None
    for token in words:
        if token.startswith("GH_REPO="):
            gh_repo = token.split("=", 1)[1]
        if token.startswith("GH_HOST="):
            gh_host = token.split("=", 1)[1]
    words = strip_prefixes(words)
    if len(words) < 2 or basename(words[0]) != "gh":
        return None
    index = 1
    while index < len(words):
        token = words[index]
        if token in {"--repo", "-R"} and index + 1 < len(words):
            gh_repo = words[index + 1]
            index += 2
            continue
        if token.startswith("--repo="):
            gh_repo = token.split("=", 1)[1]
            index += 1
            continue
        if token.startswith("GH_REPO=") or token.startswith("GH_HOST=") or ASSIGNMENT.match(token):
            index += 1
            continue
        break
    if index < len(words) and words[index] == "api":
        return parse_gh_api(words[index + 1 :])
    if len(words) - index < 2:
        return None
    pair = (words[index], words[index + 1])
    if pair not in GH_GUARDED:
        return None
    pr = None
    tail = words[index + 2 :]
    tail_index = 0
    while tail_index < len(tail):
        token = tail[tail_index]
        if token in {"--repo", "-R"} and tail_index + 1 < len(tail):
            gh_repo = tail[tail_index + 1]
            tail_index += 2
            continue
        if token.startswith("--repo="):
            gh_repo = token.split("=", 1)[1]
            tail_index += 1
            continue
        if token.startswith("-"):
            tail_index += 1
            continue
        url_repo, url_pr = pr_url_identity(token)
        if url_repo and url_pr:
            gh_repo = gh_repo or url_repo
            pr = url_pr
            break
        pr = token
        tail_index += 1
    kind = "gh_" + pair[1]
    if kind in {"gh_ready", "gh_merge"} and pr and not gh_repo:
        return Guarded(kind, cwd, "PR identity is unclear; pass --repo/-R or GH_REPO with the PR number")
    return Guarded(kind, cwd, pr=pr, gh_repo=gh_repo, gh_host=gh_host)


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


def segment_mentions_publication(words: list[str]) -> bool:
    text = " ".join(words)
    return any(term in text for term in ("push", " pr ", "pulls", "pullRequest", "merges", "api"))


def guarded_segment(words: list[str], cwd: Path, depth: int) -> Guarded | None:
    if not words:
        return None
    stripped = strip_prefixes(list(words))
    if stripped and ("$" in stripped[0] or "`" in stripped[0]) and segment_mentions_publication(stripped):
        return Guarded("unreadable", None, "unreadable command head; run the publication command directly")
    if basename(words[0]) == "cd" and len(words) >= 2:
        return Guarded("cd", resolve_path(cwd, words[1]))
    if git_mutates_state(list(words), cwd):
        return Guarded("mutation", None, "run the push as its own tool call")
    if mutating_curl_or_wget(list(words)):
        return Guarded("unreadable", None, "mutating GitHub PR API call blocked; this is a guardrail against mistakes; GitHub branch protection is the enforcement boundary")
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
    saw_mutation = False
    for segment in command_segments(command):
        found = guarded_segment(segment, current_cwd, depth)
        if not found:
            continue
        if found.kind == "cd" and found.repo:
            current_cwd = found.repo
            continue
        if found.kind == "mutation":
            saw_mutation = True
            continue
        if saw_mutation and found.kind in {"push", "gh_create", "gh_ready", "gh_merge"}:
            noun = "PR action" if found.kind.startswith("gh_") else "push"
            return Guarded(found.kind, found.repo, f"run the {noun} as its own tool call", found.heads, found.pr, found.gh_repo, found.gh_host)
        return found
    return None


def inline_reason(repo: Path, heads: list[str] | None = None) -> str | None:
    try:
        failures = []
        for head in heads or ["HEAD"]:
            checks = deterministic_checks(repo, head=head)
            failures.extend(failed_checks(checks))
    except RuntimeError as error:
        return str(error)
    except subprocess.CalledProcessError:
        return f"ship-check could not identify refs in {repo}; run the push from inside the repo"
    if failures:
        return "; ".join(f"{check['name']}: {check['summary']}" for check in failures)
    return None


# Fields `gh pr view --json` accepts (gh 2.x); an unknown field makes gh exit non-zero.
GH_PR_FIELDS = ("headRefOid", "statusCheckRollup", "url", "headRepository")


def pr_url_repo(url: str) -> str | None:
    """`owner/repo` from a PR URL such as https://github.com/owner/repo/pull/12."""
    match = re.match(r"https?://[^/]+/([^/]+/[^/]+)/pull/\d+", url)
    return match.group(1) if match else None


def check_ci(repo: Path, guarded: Guarded) -> str | None:
    try:
        local_head = git_out(repo, "rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        return f"ship-check could not identify a git repository at {repo}; run the push from inside the repo"
    args = ["gh", "pr", "view", "--json", ",".join(GH_PR_FIELDS)]
    if guarded.pr:
        args.insert(3, guarded.pr)
    if guarded.gh_repo:
        args += ["--repo", guarded.gh_repo]
    env = os.environ.copy()
    if guarded.gh_host:
        env["GH_HOST"] = guarded.gh_host
    proc = subprocess.run(args, cwd=repo, env=env, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return f"gh pr view --json headRefOid,statusCheckRollup failed; ensure gh is authenticated and run from the PR repo: {(proc.stderr or proc.stdout).strip()}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        return f"gh pr view returned invalid JSON: {error}"
    if guarded.pr:
        pr_head = data.get("headRefOid")
        if subprocess.run(["git", "cat-file", "-e", f"{pr_head}^{{commit}}"], cwd=repo, capture_output=True).returncode != 0:
            return "PR is not from this repo: PR head sha is not present locally"
        base_repo = pr_url_repo(str(data.get("url") or ""))
        remotes = subprocess.run(["git", "remote", "-v"], cwd=repo, text=True, capture_output=True).stdout
        if base_repo and base_repo not in remotes:
            return "PR is not from this repo: PR base repo does not match a local remote"
    expected = data.get("headRefOid") if guarded.pr else local_head
    if data.get("headRefOid") != expected:
        return f"PR head {data.get('headRefOid')} does not match expected head {expected}"
    checks = data.get("statusCheckRollup") or []
    if not checks:
        return f"no status checks found for PR head {expected}; wait for required CI before ready/merge"
    bad = []
    for check in checks:
        typename = check.get("__typename")
        if typename == "StatusContext":
            ok = str(check.get("state") or "").upper() == "SUCCESS"
        else:
            ok = str(check.get("conclusion") or "").upper() == "SUCCESS"
        if not ok:
            bad.append(check.get("name") or check.get("context") or json.dumps(check, sort_keys=True))
    if bad:
        return f"status checks are not all SUCCESS for PR head {expected}: {', '.join(map(str, bad))}"
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
    reason = inline_reason(guarded.repo, guarded.heads)
    if reason:
        return deny(reason)
    if guarded.kind in {"gh_ready", "gh_merge"}:
        ci_reason = check_ci(guarded.repo, guarded)
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
