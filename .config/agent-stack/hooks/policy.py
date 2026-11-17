#!/usr/bin/env python3
"""One pre/post-tool policy guard, shared by every harness and host.

Reads a hook payload as JSON on stdin and prints a JSON verdict on stdout
(nothing at all means "allow"). Vibe calls it directly as a `[[hooks]]`
command; Pi calls it through the `vibe-policy` extension.

Only generic rules live here. Site-specific roots come from an untracked
`~/.config/agent-stack/policy.local.json` (see policy.local.example.json).
With no such file the broad-scan rules still cover `/`, `/mnt` and `$HOME`,
and the repo-scoped rules stay off.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from typing import Any


Response = dict[str, Any]
Payload = dict[str, Any]


# -- site configuration ------------------------------------------------------

POLICY_LOCAL_ENV = "AGENT_STACK_POLICY_LOCAL"
DEFAULT_POLICY_LOCAL = "~/.config/agent-stack/policy.local.json"

# Roots that are too broad to scan on any machine. A site adds its own shared
# mounts and home-relative directories in policy.local.json.
GENERIC_BROAD_ROOTS = ("/", "/mnt", "~")


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _normalized_root(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def load_site_config(path: str | None = None) -> dict[str, Any]:
    """Broad roots and repo roots for this machine.

    A missing file is the normal case on a fresh host and leaves only the
    generic rules. An unreadable or malformed file would otherwise brick every
    session the hook guards, so it warns on stderr and falls back to the same
    generic rules rather than raising.
    """
    source = path or os.environ.get(POLICY_LOCAL_ENV) or DEFAULT_POLICY_LOCAL
    local: dict[str, Any] = {}
    expanded = os.path.expanduser(source)
    if os.path.isfile(expanded):
        try:
            parsed = json.loads(open(expanded, encoding="utf-8").read())
        except (OSError, ValueError) as error:
            print(f"policy.py: ignoring unreadable {expanded}: {error}", file=sys.stderr)
            parsed = None
        if isinstance(parsed, dict):
            local = parsed
    broad = GENERIC_BROAD_ROOTS + _string_list(local.get("broad_roots"))
    return {
        "broad_roots": frozenset(_normalized_root(root) for root in broad),
        "repo_roots": tuple(_normalized_root(root) for root in _string_list(local.get("repo_roots"))),
    }


SITE = load_site_config()
BROAD_ROOTS: frozenset[str] = SITE["broad_roots"]
REPO_ROOTS: tuple[str, ...] = SITE["repo_roots"]


# -- tool names --------------------------------------------------------------

# Vibe 3.x qualifies tool names (`file_system.bash`); Pi and older Vibe send
# them bare. Background commands arrive as `process_start` or `process.start`.
BASH_TOOL_LEAVES = frozenset({"bash", "process_start"})
PROCESS_BASH_LEAVES = frozenset({"start"})
# `write` is Pi's name for the tool Vibe calls `write_file`.
FILE_WRITE_TOOL_LEAVES = frozenset({"edit", "write_file", "write", "search_replace"})
COMMAND_KEYS = ("command", "cmd")


def tool_kind(tool_name: str) -> str | None:
    """`bash`, `write`, or None, for both bare and group-qualified names."""
    group, _, leaf = tool_name.strip().rpartition(".")
    if leaf in BASH_TOOL_LEAVES or (group == "process" and leaf in PROCESS_BASH_LEAVES):
        return "bash"
    if leaf in FILE_WRITE_TOOL_LEAVES:
        return "write"
    return None


# -- patterns ----------------------------------------------------------------

SHELL_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
UNRESOLVED_EXPANSION = re.compile(r"[$`]")
EXPANSION_PASSES = 8
COMMAND_SEPARATORS = {";", "&", "&&", "|", "||", "\n", "(", ")", "{", "}"}
PIPE_SEPARATORS = {"|", "|&"}
GROUPING_SEPARATORS = {"(", ")", "{", "}"}
SHELL_LEADING_RESERVED_WORDS = {"if", "then", "else", "elif", "while", "until", "do"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
GIT_GLOBAL_OPTIONS_WITH_VALUE = {"-C", "-c"}
FIND_PRE_ROOT_OPTIONS = {"-H", "-L", "-P"}
GREP_LONG_RECURSIVE_OPTIONS = {"--recursive", "--dereference-recursive"}
GREP_OPTIONS_WITH_VALUE = {
    "-A",
    "-B",
    "-C",
    "-D",
    "-d",
    "-e",
    "-f",
    "-m",
    "--after-context",
    "--before-context",
    "--binary-files",
    "--context",
    "--devices",
    "--directories",
    "--exclude",
    "--exclude-dir",
    "--file",
    "--include",
    "--label",
    "--max-count",
    "--regexp",
}
GREP_PATTERN_OPTIONS = {"-e", "-f", "--regexp", "--file"}
GREP_SHORT_OPTIONS_WITH_ATTACHED_VALUE = ("-A", "-B", "-C", "-D", "-d", "-e", "-f", "-m")
GREP_SHORT_PATTERN_OPTIONS = {"e", "f"}
GREP_SHORT_NON_PATTERN_OPTIONS_WITH_ATTACHED_VALUE = {"A", "B", "C", "D", "d", "m"}
GREP_DIRECTORIES_OPTIONS = {"-d", "--directories"}
GREP_RECURSIVE_DIRECTORIES_VALUE = "recurse"

SHELL_READ_SEARCH = re.compile(r"(^|[;&|]\s*)(grep\b|find\b|rg\b)")
SEARCH_EXECUTABLES = {"grep", "find", "rg"}

LOCK_OR_CONFIG_PATTERNS = (
    re.compile(r"\bpip\s+install\b"),
    re.compile(r"\bnpm\s+install\b"),
    re.compile(r"(^|/)(uv\.lock|package-lock\.json|poetry\.lock|pyproject\.toml|config\.toml|opencode\.jsonc?)$"),
)

# Pathspecs that mean "everything tracked here", so a discard scoped to one of them is
# no narrower than a tree-wide discard. Anything else names specific files and is allowed.
WHOLE_TREE_PATHSPECS = {".", "./", "..", "*", ":/", ":/.", ":(top)"}

SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"bkua_[A-Fa-f0-9]{16,}"),
    re.compile(r"lin_api_[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)(api[_-]?key|token|authorization)\s*[=:]\s*['\"]?[^'\"\s,}]{12,}"),
    # GitHub tokens: ghp_/gho_/ghu_/ghs_/ghr_ and fine-grained PATs.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)

LOCK_OR_CONFIG_NUDGE = (
    "This touches a lock/config file or package install in a managed repo. Proceeding is fine, but say so "
    "explicitly in your response, and name which dependencies or lockfiles changed, so the user can review it."
)

# Signing bypass. Keys are matched case-insensitively, as git does.
SIGNING_CONFIG_KEYS = {"commit.gpgsign", "tag.gpgsign", "push.gpgsign"}
FALSE_CONFIG_VALUES = {"false", "off", "no", "0", ""}

# Shell tracing with secrets in scope. `set -x` echoes every expanded word, so a
# traced command that reads a token writes that token to the transcript.
TRACE_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}

# `bash -c "..."` hides its payload from a tokeniser that only looks at the outer
# words, so every rule here can be bypassed by one level of quoting. Inner
# strings are parsed and judged by the same rules, up to this nesting depth.
NESTING_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
MAX_NESTING_DEPTH = 2
NESTED_NOTE = "(found inside a nested `bash -c`/`eval` string)"

# Prefixes that run another command without changing what it does. Stripping
# them means `sudo rm -rf /` is judged as `rm -rf /` by every rule at once,
# instead of each rule needing its own sudo clause.
COMMAND_PREFIXES = {
    "sudo", "doas", "env", "nohup", "command", "exec", "stdbuf", "nice", "ionice",
    "setsid", "time", "xargs", "busybox",
}
# Options these prefixes take that consume the following word.
PREFIX_OPTIONS_WITH_VALUE = {
    "-u", "-g", "-U", "-n", "-i", "-o", "-e", "-I", "-L", "-P", "-a", "-d", "-S", "-C", "--chdir",
    "--user", "--group", "--max-procs", "--replace", "--arg-file", "--delimiter", "--max-args",
}
# `timeout` takes a duration operand before the command.
PREFIX_WITH_DURATION = {"timeout"}
DURATION_OPERAND = re.compile(r"\d+(\.\d+)?[smhd]?")

# A shell reading its script from stdin or a here-document runs text the
# tokeniser never sees as a command.
STDIN_FED_SHELL_NOTE = (
    "Blocked: this feeds a script into a shell through a pipe, here-string or here-document, so "
    "the policy guard cannot see what it runs. Put the commands in the tool call directly."
)
HEREDOC_OPERATORS = ("<<<", "<<-", "<<")
REMOTE_SHELL_COMMANDS = {"ssh", "rsh", "docker", "kubectl", "podman"}
CONTAINER_COMMANDS = {"docker", "kubectl", "podman"}
CONTAINER_EXEC_VERBS = {"exec", "run"}
REMOTE_OPTIONS_WITH_VALUE = {
    "-p", "-i", "-l", "-o", "-F", "-c", "-b", "-D", "-E", "-I", "-J", "-L", "-m", "-O",
    "-Q", "-R", "-S", "-W", "-w", "--port", "--login-name",
}
CONTAINER_OPTIONS_WITH_VALUE = {
    "-n", "--namespace", "--context", "-c", "--container", "-u", "--user", "-e", "--env",
    "-w", "--workdir", "--kubeconfig",
}

# Force-pushing a shared branch rewrites history other people have pulled.
PROTECTED_BRANCHES = {"main", "master"}
PROTECTED_BRANCH_PREFIXES = ("release/",)
PUSH_FORCE_FLAGS = {"--force", "-f", "--force-with-lease", "--force-if-includes"}
PUSH_OPTIONS_WITH_VALUE = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}

SECRET_NAME = re.compile(r"(?i)(^|[^A-Za-z])(secret|token|key|password|passwd|credential)s?([^A-Za-z]|$)")
# `.env`, `.env.production`, `prod.env`. Not the `env` command.
DOTENV_FILE = re.compile(r"(?i)^\.env(\.[^/]*)?$|\.env$")


# -- responses ---------------------------------------------------------------


def allow_with_context(text: str) -> Response:
    return {"hook_specific_output": {"additional_context": text}}


def deny(reason: str) -> Response:
    return {"decision": "deny", "reason": reason}


def get_tool_input(payload: Payload) -> dict[str, Any]:
    value = payload.get("tool_input")
    if isinstance(value, dict):
        return value
    return {}


def tool_command(tool_input: dict[str, Any]) -> str:
    for key in COMMAND_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str):
            return value
    return ""


def handle_payload(payload: Payload) -> Response | None:
    event = str(payload.get("hook_event_name", ""))
    if event == "pre_tool":
        return handle_pre_tool(payload)
    if event == "post_tool":
        return handle_post_tool(payload)
    return None


def handle_pre_tool(payload: Payload) -> Response | None:
    tool_name = str(payload.get("tool_name", ""))
    kind = tool_kind(tool_name)
    tool_input = get_tool_input(payload)
    cwd = str(payload.get("cwd", ""))
    if kind == "bash":
        return check_bash_command(tool_command(tool_input), cwd)
    if kind == "write":
        return check_mutating_file_tool(tool_input, cwd)
    # An unrecognised tool carrying a command string runs a shell by some other
    # name. Judging it as bash is the safe default: a new or renamed tool must
    # not be a way past the guard.
    if kind is None and tool_command(tool_input):
        return check_bash_command(tool_command(tool_input), cwd)
    return None


def nested_command_strings(command: str) -> list[str] | None:
    """Payloads of `bash -c "..."`, `eval "..."` and friends, one level down.

    None means a wrapper was found but its payload could not be read, so the
    caller must not treat the command as checked.
    """
    tokens = shell_tokens(command)
    if tokens is None:
        return None
    payloads: list[str] = []
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        executable = os.path.basename(segment[index])
        args = segment[index + 1 :]
        if executable == "eval":
            if not args:
                continue
            # `eval a b` concatenates its words into one command.
            payloads.append(" ".join(args))
            continue
        if executable not in NESTING_SHELLS:
            continue
        for position, token in enumerate(args):
            if token in {"-c", "--command"}:
                if position + 1 >= len(args):
                    return None
                payloads.append(args[position + 1])
                break
            if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
                if position + 1 >= len(args):
                    return None
                payloads.append(args[position + 1])
                break
    return payloads


def shell_reads_script_from_stdin(command: str) -> bool:
    """A shell whose script arrives by pipe, here-string or here-document.

    `echo "rm -rf /" | sh` and `bash <<< "..."` run text that never appears as
    a command token, so no rule can see it.
    """
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    for segment, reads_pipe in command_segments_with_stdin(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        if os.path.basename(segment[index]) not in NESTING_SHELLS:
            continue
        args = segment[index + 1 :]
        # An explicit `-c` payload is read by the nesting check instead.
        if any(token in {"-c", "--command"} for token in args):
            continue
        if any(token.startswith("-") and not token.startswith("--") and "c" in token[1:] for token in args):
            continue
        # A script file operand is a normal invocation, not stdin.
        if reads_pipe and not [token for token in args if not token.startswith("-")]:
            return True
        if any(operator in token for token in segment for operator in HEREDOC_OPERATORS):
            return True
    # Heredoc bodies are stripped of their operator by the lexer in some forms.
    return any(operator in command for operator in HEREDOC_OPERATORS) and any(
        re.search(rf"(^|[\s;&|(]){shell}(\s|$)", command) for shell in NESTING_SHELLS
    )


def remote_shell_payload(command: str) -> list[str]:
    """Command words handed to ssh/docker/kubectl to run elsewhere."""
    tokens = shell_tokens(command)
    if tokens is None:
        return []
    payloads: list[str] = []
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        executable = os.path.basename(segment[index])
        if executable not in REMOTE_SHELL_COMMANDS:
            continue
        # Keep every word after the host, flags included: dropping `-rf` from
        # `ssh host rm -rf /` would leave a harmless-looking `rm /`.
        args = segment[index + 1 :]
        position = 0
        # `docker exec c cmd` / `kubectl exec pod -- cmd`: step over the verb.
        if executable in CONTAINER_COMMANDS:
            while position < len(args) and args[position].startswith("-"):
                position += 2 if args[position] in CONTAINER_OPTIONS_WITH_VALUE else 1
            if position < len(args) and args[position] in CONTAINER_EXEC_VERBS:
                position += 1
            else:
                continue
        while position < len(args) and args[position].startswith("-"):
            position += 2 if args[position] in REMOTE_OPTIONS_WITH_VALUE else 1
        # args[position] is the host/container; the rest is the remote command.
        remote = args[position + 1 :]
        if remote and remote[0] == "--":
            remote = remote[1:]
        if remote:
            payloads.append(" ".join(shlex.quote(token) for token in remote))
    return payloads


def check_bash_command(command: str, cwd: str, depth: int = 0) -> Response | None:
    """Judge a command, then judge anything it hides inside `bash -c`/`eval`."""
    verdict = check_bash_command_text(command, cwd)
    if verdict is not None and verdict.get("decision") == "deny":
        return verdict

    if shell_reads_script_from_stdin(command):
        return deny(STDIN_FED_SHELL_NOTE)

    nested = nested_command_strings(command)
    if nested is None:
        return deny(
            "Blocked: this command wraps another command in a way the policy guard cannot read, "
            "so its contents cannot be checked. Run the inner command directly."
        )
    if nested and depth >= MAX_NESTING_DEPTH:
        return deny(
            f"Blocked: shell wrappers nested more than {MAX_NESTING_DEPTH} deep cannot be checked "
            "reliably. Run the command directly instead of wrapping it in `bash -c`/`eval`."
        )
    for payload in nested + remote_shell_payload(command):
        nested_verdict = check_bash_command(payload, cwd, depth + 1)
        if nested_verdict is not None and nested_verdict.get("decision") == "deny":
            reason = nested_verdict["reason"]
            # Only the outermost frame annotates, so the note appears once.
            if NESTED_NOTE in reason:
                return deny(reason)
            return deny(f"{reason} {NESTED_NOTE}")

    return verdict


def check_bash_command_text(command: str, cwd: str) -> Response | None:
    if force_pushes_protected_branch(command):
        return deny(
            "Blocked a force-push to a protected branch. This rewrites history others have already "
            "pulled. Ask Hugo before force-pushing main/master/release/*; push to a feature branch "
            "and open a PR instead."
        )
    if uses_destructive_rm(command, cwd) or uses_destructive_git(command):
        return deny(
            "Blocked destructive shell command. Use a narrower non-destructive command, "
            "or ask explicitly if this really needs to discard local state."
        )
    if bypasses_commit_signing(command):
        return deny(
            "Blocked a commit-signing bypass. Keep signing on and fix the signer instead "
            "(`git config gpg.format` says which one; check SSH_AUTH_SOCK or GNUPGHOME)."
        )
    if traces_shell_with_secrets(command):
        return deny(
            "Blocked `set -x`/`-x` tracing on a command that reads a secret: tracing echoes the expanded "
            "value into the transcript and the logs. Drop the trace, or read the secret in an untraced "
            "subshell (`set +x` around it)."
        )
    if is_broad_scan(command, cwd):
        return deny(
            "This find/grep/rg/du/ls command is too broad for the home/repo root. Use Vibe's `grep`/`read_file` tools, "
            "or narrow the shell command with a specific subdirectory, an include pattern, and `-maxdepth`/`--max-depth`."
        )
    if creates_worktree_inside_repo(command, cwd):
        return deny(
            "Create worktrees outside the source repository checkout, not inside a managed repo root."
        )
    if lock_or_config_command_is_notable(command, cwd):
        return allow_with_context(LOCK_OR_CONFIG_NUDGE)
    if cwd_is_under_repo_root(cwd) and uses_standalone_python(command):
        return deny("Use `uv run python ...` in this repo instead of standalone `python` or `python3`.")
    if uses_shell_read_or_search(command):
        return {
            "system_message": "Prefer Vibe grep/read_file tools over shell grep/find/rg unless the shell pipeline is genuinely needed."
        }
    return None


def is_broad_scan(command: str, cwd: str) -> bool:
    return (
        is_broad_find(command, cwd)
        or is_broad_recursive_grep(command, cwd)
        or is_broad_rg(command, cwd)
        or is_broad_du(command, cwd)
        or is_broad_recursive_ls(command, cwd)
    )


# -- shell parsing -----------------------------------------------------------


def rejoin_brace_expansions(tokens: list[str]) -> list[str]:
    """Put `${VAR}` back together after lexing.

    `{` and `}` are punctuation so `{ cmd; }` groups split correctly, but that
    also shreds `${HOME}` into `$`, `{`, `HOME`, `}`. Left split, the root of
    `find ${HOME}` never reaches variable expansion and the scan is allowed.
    """
    merged: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            token.endswith("$")
            and index + 3 < len(tokens)
            and tokens[index + 1] == "{"
            and tokens[index + 3] == "}"
        ):
            merged.append(f"{token}{{{tokens[index + 2]}}}")
            index += 4
            continue
        merged.append(token)
        index += 1
    return merged


def shell_tokens(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n(){}")
        lexer.whitespace_split = True
        lexer.whitespace = " \t\r"
        lexer.commenters = ""
        return rejoin_brace_expansions(list(lexer))
    except ValueError:
        return None


def is_shell_separator(token: str) -> bool:
    return token in COMMAND_SEPARATORS or bool(token) and all(character in ";&|\n(){}" for character in token)


def command_segments_with_stdin(tokens: list[str]) -> list[tuple[list[str], bool]]:
    """Segments paired with whether the segment receives a pipe on stdin.

    Grouping tokens are transparent so `a | (rg p)` still counts as piped.
    """
    segments: list[tuple[list[str], bool]] = []
    segment: list[str] = []
    piped = False
    for token in tokens:
        if is_shell_separator(token):
            if segment:
                segments.append((segment, piped))
                segment = []
                piped = False
            if token not in GROUPING_SEPARATORS:
                piped = token in PIPE_SEPARATORS
            continue
        segment.append(token)
    if segment:
        segments.append((segment, piped))
    return segments


def command_segments(tokens: list[str]) -> list[list[str]]:
    return [segment for segment, _ in command_segments_with_stdin(tokens)]


def shell_executable_index(segment: list[str]) -> int | None:
    """Index of the real command, past assignments, keywords and wrappers.

    Every rule calls this, so stripping `sudo`/`env`/`timeout` here makes
    `sudo rm -rf /` judged as `rm -rf /` by all of them at once.
    """
    index = 0
    while index < len(segment):
        token = segment[index]
        if ENV_ASSIGNMENT.match(token) or token in SHELL_LEADING_RESERVED_WORDS:
            index += 1
            continue
        name = os.path.basename(token)
        if name in COMMAND_PREFIXES or name in PREFIX_WITH_DURATION:
            index += 1
            # Skip the prefix's own options, and the words they consume.
            while index < len(segment) and segment[index].startswith("-"):
                consumes = segment[index] in PREFIX_OPTIONS_WITH_VALUE
                index += 2 if consumes and index + 1 < len(segment) else 1
            if name in PREFIX_WITH_DURATION:
                # `timeout 5 cmd`: step over the duration operand.
                if index < len(segment) and DURATION_OPERAND.fullmatch(segment[index]):
                    index += 1
            if name == "env":
                while index < len(segment) and ENV_ASSIGNMENT.match(segment[index]):
                    index += 1
            continue
        break
    if index >= len(segment):
        return None
    return index


def is_executable_named(token: str, name: str) -> bool:
    return os.path.basename(token) == name


def executable_segments(command: str, name: str) -> list[list[str]]:
    """Argument lists of every segment whose executable is `name`."""
    return [args for args, _, _ in executable_frames(command, name, "")]


def executable_frames(command: str, name: str, cwd: str) -> list[tuple[list[str], str, dict[str, str]]]:
    """Every `name` invocation with the cwd and assignments in force at it.

    `cd /tmp && find .` must judge `.` as /tmp, and `find $HOME` must judge the
    expanded value, so scan rules need more than the raw argument list.
    """
    tokens = shell_tokens(command)
    if tokens is None:
        return []
    assignments = shell_assignments(tokens)
    frames: list[tuple[list[str], str, dict[str, str]]] = []
    effective_cwd = cwd
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        executable = os.path.basename(segment[index])
        args = segment[index + 1 :]
        if executable == "cd" and args:
            target = expand_shell_variables(args[0], assignments)
            if not UNRESOLVED_EXPANSION.search(target):
                effective_cwd = normalize_command_path(target, effective_cwd)
            continue
        if is_executable_named(segment[index], name):
            frames.append((args, effective_cwd, assignments))
    return frames


# -- destructive rm / git ----------------------------------------------------


def rm_flag_effects(token: str) -> tuple[bool, bool]:
    if token in {"--recursive", "--force"}:
        return token == "--recursive", token == "--force"
    if token.startswith("--") or not token.startswith("-") or token == "-":
        return False, False
    flags = token[1:]
    return any(character in flags for character in ("r", "R")), "f" in flags


def rm_args_are_recursive_force(args: list[str]) -> bool:
    recursive = False
    force = False
    for token in args:
        if token == "--":
            break
        token_recursive, token_force = rm_flag_effects(token)
        recursive = recursive or token_recursive
        force = force or token_force
        if recursive and force:
            return True
    return False


# Regenerable build and cache directories. Deleting one costs a rebuild, so
# blocking it trains people to work around the guard for no safety gain.
DISPOSABLE_DIRECTORIES = {
    "node_modules", ".pytest_cache", "__pycache__", ".ruff_cache", ".mypy_cache",
    "dist", "build", "target", ".venv",
}


def rm_targets_are_all_disposable(args: list[str], cwd: str) -> bool:
    """Whether every operand is a regenerable directory directly in the cwd.

    Scoped deliberately tightly: a direct child only, so `../build` and
    `/etc/build` stay blocked, and never a symlink, so a planted
    `node_modules -> /` link cannot borrow the exemption.
    """
    operands: list[str] = []
    after_double_dash = False
    for token in args:
        if after_double_dash:
            operands.append(token)
            continue
        if token == "--":
            after_double_dash = True
            continue
        if token.startswith("-") and token != "-":
            continue
        operands.append(token)
    if not operands:
        return False
    for token in operands:
        if UNRESOLVED_EXPANSION.search(token):
            return False
        resolved = normalize_command_path(token, cwd)
        # Judge the resolved path, not the spelling: `./build`, `build/` and
        # `sub/../build` must all be decided the same way.
        if os.path.basename(resolved) not in DISPOSABLE_DIRECTORIES:
            return False
        # A direct child of the cwd only, so `../build` and `sub/build` stay
        # blocked even though they end in a disposable name.
        if os.path.dirname(resolved) != os.path.normpath(cwd or os.getcwd()):
            return False
        # A symlink wearing a disposable name must not borrow the exemption.
        if os.path.islink(resolved):
            return False
    return True


def uses_destructive_rm(command: str, cwd: str = "") -> bool:
    for args, frame_cwd, _ in executable_frames(command, "rm", cwd):
        if not rm_args_are_recursive_force(args):
            continue
        if rm_targets_are_all_disposable(args, frame_cwd):
            continue
        return True
    return False


def git_command_args(segment: list[str]) -> list[str] | None:
    index = shell_executable_index(segment)
    if index is None or segment[index] != "git":
        return None
    index += 1
    while index < len(segment):
        token = segment[index]
        if token in GIT_GLOBAL_OPTIONS_WITH_VALUE and index + 1 < len(segment):
            index += 2
            continue
        if token.startswith("-C") and token != "-C":
            index += 1
            continue
        break
    return segment[index:]


def git_pathspec_args(args: list[str]) -> list[str]:
    if "--" in args:
        return args[args.index("--") + 1 :]
    return [token for token in args if not token.startswith("-")]


def git_checkout_pathspec_args(args: list[str]) -> list[str]:
    """Pathspecs of `git checkout`, with or without the `--` separator.

    After `--` every operand is a pathspec. Without it git treats operands as a
    revision first, so only a whole-tree spec like `.` is a worktree discard:
    returning [] for `git checkout main` keeps branch switching allowed, and
    bare `git checkout` likewise names nothing.
    """
    if "--" in args:
        return args[args.index("--") + 1 :]
    operands = [token for token in args if not token.startswith("-")]
    return [token for token in operands if token in WHOLE_TREE_PATHSPECS or token.rstrip("/") in WHOLE_TREE_PATHSPECS]


def discards_whole_tree(paths: list[str]) -> bool:
    if not paths:
        return True
    return any(
        path in WHOLE_TREE_PATHSPECS or path.rstrip("/") in WHOLE_TREE_PATHSPECS or path == "/"
        for path in paths
    )


def restore_touches_worktree(args: list[str]) -> bool:
    if "--worktree" in args or "-W" in args:
        return True
    return not ("--staged" in args or "-S" in args)


def clean_args_are_forced(args: list[str]) -> bool:
    force = False
    for token in args:
        if token == "--":
            break
        if token == "--dry-run":
            return False
        if token == "--force":
            force = True
            continue
        if token.startswith("--") or not token.startswith("-") or token == "-":
            continue
        flags = token[1:]
        if "n" in flags:
            return False
        force = force or "f" in flags
    return force


def uses_destructive_git(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    for segment in command_segments(tokens):
        args = git_command_args(segment)
        if not args:
            continue
        subcommand = args[0]
        rest = args[1:]
        # `reset --hard` always resets the whole tree; there is no path-scoped form.
        if subcommand == "reset" and "--hard" in rest:
            return True
        # `git checkout .` discards the worktree exactly like `git checkout -- .`;
        # requiring the `--` separator missed the commoner spelling.
        if subcommand == "checkout":
            if "-f" in rest or "--force" in rest:
                return True
            if "--" in rest:
                if discards_whole_tree(git_pathspec_args(rest)):
                    return True
            # Without `--`, an empty result means the command named a revision
            # or nothing, so it is not a worktree discard.
            elif git_checkout_pathspec_args(rest):
                return True
        if subcommand == "switch" and ("--discard-changes" in rest or "-f" in rest or "--force" in rest):
            return True
        # Dropped stash entries are unrecoverable without reflog spelunking.
        if subcommand == "stash" and any(word in rest for word in ("drop", "clear")):
            return True
        if subcommand == "restore" and restore_touches_worktree(rest) and discards_whole_tree(git_pathspec_args(rest)):
            return True
        if subcommand == "clean" and clean_args_are_forced(rest) and discards_whole_tree(git_pathspec_args(rest)):
            return True
    return False


# -- commit signing ----------------------------------------------------------


def config_pair_disables_signing(text: str) -> bool:
    key, separator, value = text.partition("=")
    if not separator:
        return False
    return key.strip().lower() in SIGNING_CONFIG_KEYS and value.strip().lower() in FALSE_CONFIG_VALUES


def git_config_sets_signing_off(args: list[str]) -> bool:
    """`git config [--scope] commit.gpgsign false`, in any of its scopes."""
    if not args or args[0] != "config":
        return False
    positional = [token for token in args[1:] if not token.startswith("-")]
    if positional and positional[0] in {"set", "get", "unset"}:
        positional = positional[1:]
    return (
        len(positional) >= 2
        and positional[0].lower() in SIGNING_CONFIG_KEYS
        and positional[1].strip().lower() in FALSE_CONFIG_VALUES
    )


def bypasses_commit_signing(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None or not is_executable_named(segment[index], "git"):
            continue
        args = segment[index + 1 :]
        for position, token in enumerate(args):
            # `--no-gpg-sign` and git's `--no-gpg-sign=<keyid>` form.
            if token == "--no-gpg-sign" or token.startswith("--no-gpg-sign="):
                return True
            if token == "-c" and position + 1 < len(args) and config_pair_disables_signing(args[position + 1]):
                return True
            if token.startswith("-c") and token != "-c" and config_pair_disables_signing(token[2:]):
                return True
        if git_config_sets_signing_off(git_command_args(segment) or []):
            return True
    return False


# -- force push --------------------------------------------------------------


def branch_is_protected(name: str) -> bool:
    """Whether a refspec destination names a shared branch."""
    ref = name.strip()
    if not ref:
        return False
    ref = ref.lstrip("+")
    # A refspec's destination is what gets overwritten: `local:remote`.
    if ":" in ref:
        ref = ref.rpartition(":")[2]
    for prefix in ("refs/heads/", "refs/remotes/"):
        if ref.startswith(prefix):
            ref = ref[len(prefix) :]
    return ref in PROTECTED_BRANCHES or ref.startswith(PROTECTED_BRANCH_PREFIXES)


def push_refspecs(args: list[str]) -> list[str]:
    """Operands of `git push`, minus the remote name and option values."""
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
        if token.startswith("-"):
            index += 1
            continue
        operands.append(token)
        index += 1
    # `--repo=X` / `--repo X` supplies the remote, so every operand is a refspec.
    if any(token == "--repo" or token.startswith("--repo=") for token in args):
        return operands
    # Otherwise the first operand is the remote; the rest are refspecs.
    return operands[1:] if len(operands) > 1 else []


def force_pushes_protected_branch(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    for segment in command_segments(tokens):
        args = git_command_args(segment)
        if not args or args[0] != "push":
            continue
        rest = args[1:]
        refspecs = push_refspecs(rest)
        flag_forced = any(
            token in PUSH_FORCE_FLAGS or token.startswith("--force-with-lease=") for token in rest
        )
        # A leading `+` on a refspec is force, per-ref.
        plus_forced = [ref for ref in refspecs if ref.startswith("+")]
        if plus_forced and any(branch_is_protected(ref) for ref in plus_forced):
            return True
        if not flag_forced:
            continue
        if any(branch_is_protected(ref) for ref in refspecs):
            return True
        # `git push --force` with no refspec pushes the current branch, which is
        # unknowable here. The push itself is gated by ship-check, so stay quiet.
    return False


# -- shell tracing with secrets ----------------------------------------------


def segment_enables_trace(segment: list[str], index: int) -> bool:
    executable = os.path.basename(segment[index])
    args = segment[index + 1 :]
    if executable == "set":
        for position, token in enumerate(args):
            if token.startswith("-") and not token.startswith("--") and "x" in token[1:]:
                return True
            if token == "-o" and position + 1 < len(args) and args[position + 1] == "xtrace":
                return True
        return False
    if executable in TRACE_SHELLS:
        return any(
            token.startswith("-") and not token.startswith("--") and "x" in token[1:] for token in args
        )
    return False


def references_a_secret(tokens: list[str]) -> bool:
    for token in tokens:
        for match in SHELL_VARIABLE.finditer(token):
            if SECRET_NAME.search(match.group(1) or match.group(2) or ""):
                return True
        if ENV_ASSIGNMENT.match(token) and SECRET_NAME.search(token.partition("=")[0]):
            return True
        basename = os.path.basename(token)
        if DOTENV_FILE.search(basename) or SECRET_NAME.search(basename):
            return True
    return False


def traces_shell_with_secrets(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    segments = command_segments(tokens)
    traced = False
    for segment in segments:
        index = shell_executable_index(segment)
        if index is not None and segment_enables_trace(segment, index):
            traced = True
            break
    return traced and references_a_secret([token for segment in segments for token in segment])


# -- broad scans -------------------------------------------------------------


def shell_assignments(tokens: list[str]) -> dict[str, str]:
    """Literal `name=value` assignments appearing anywhere in the command."""
    assignments: dict[str, str] = {}
    for segment in command_segments(tokens):
        for token in segment:
            if not ENV_ASSIGNMENT.match(token):
                break
            name, _, value = token.partition("=")
            assignments[name] = value
    return assignments


def expand_shell_variables(value: str, assignments: dict[str, str]) -> str:
    """Resolve $VAR/${VAR} from the command's own assignments, then the environment.

    Unknown names are left untouched so callers can detect that the real path is
    not knowable and decline to judge it.
    """
    for _ in range(EXPANSION_PASSES):
        match = SHELL_VARIABLE.search(value)
        if match is None:
            break
        expanded = SHELL_VARIABLE.sub(
            lambda found: (
                assignments.get(
                    found.group(1) or found.group(2),
                    os.environ.get(found.group(1) or found.group(2), found.group(0)),
                )
            ),
            value,
        )
        if expanded == value:
            break
        value = expanded
    return value


def normalize_command_path(path: str, cwd: str) -> str:
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd or os.getcwd(), expanded)
    return os.path.normpath(expanded)


def path_is_or_under(path: str, root: str) -> bool:
    normalized_path = os.path.normpath(path)
    normalized_root = os.path.normpath(root)
    try:
        return os.path.commonpath((normalized_path, normalized_root)) == normalized_root
    except ValueError:
        return False


def is_broad_root(path: str, cwd: str, assignments: dict[str, str] | None = None) -> bool:
    """Whether a scan root is one of the configured broad roots.

    `$HOME` and `${VAR}` are expanded first, so `find $HOME` is judged exactly
    like `find ~`. An unresolvable name is not judged: the real path is unknown
    and denying it would block correct commands.
    """
    expanded = expand_shell_variables(path, assignments or {})
    if UNRESOLVED_EXPANSION.search(expanded):
        return False
    return normalize_command_path(expanded, cwd) in BROAD_ROOTS


def find_roots(args: list[str]) -> list[str]:
    index = 0
    while index < len(args) and args[index] in FIND_PRE_ROOT_OPTIONS:
        index += 1

    roots: list[str] = []
    while index < len(args):
        token = args[index]
        if token.startswith("-") or token in {"!", "(", ")"}:
            break
        roots.append(token)
        index += 1

    return roots or ["."]


def is_broad_find(command: str, cwd: str = "") -> bool:
    for args, frame_cwd, assignments in executable_frames(command, "find", cwd):
        if "-maxdepth" in args:
            continue
        if any(is_broad_root(root, frame_cwd, assignments) for root in find_roots(args)):
            return True
    return False


def grep_option_is_recursive(token: str) -> bool:
    if token in GREP_LONG_RECURSIVE_OPTIONS:
        return True
    if token == f"--directories={GREP_RECURSIVE_DIRECTORIES_VALUE}":
        return True
    if token.startswith("-d") and token[2:] == GREP_RECURSIVE_DIRECTORIES_VALUE:
        return True
    if token.startswith("--"):
        return False
    if any(token.startswith(prefix) and token != prefix for prefix in GREP_SHORT_OPTIONS_WITH_ATTACHED_VALUE):
        return False
    return token.startswith("-") and any(character in token[1:] for character in ("r", "R"))


def grep_option_value_is_recursive(token: str, value: str | None) -> bool:
    return token in GREP_DIRECTORIES_OPTIONS and value == GREP_RECURSIVE_DIRECTORIES_VALUE


def grep_option_consumes_next(token: str) -> bool:
    return token in GREP_OPTIONS_WITH_VALUE


def grep_short_cluster_sets_attached_pattern(token: str) -> bool:
    if token.startswith("--") or not token.startswith("-") or token == "-":
        return False

    options = token[1:]
    for index, option in enumerate(options):
        if option in GREP_SHORT_PATTERN_OPTIONS:
            return index + 1 < len(options)
        if option in GREP_SHORT_NON_PATTERN_OPTIONS_WITH_ATTACHED_VALUE:
            return False
    return False


def grep_option_sets_pattern(token: str) -> bool:
    return (
        token in GREP_PATTERN_OPTIONS
        or token.startswith("-e")
        and token != "-e"
        or token.startswith("-f")
        and token != "-f"
        or token.startswith("--regexp=")
        or token.startswith("--file=")
        or grep_short_cluster_sets_attached_pattern(token)
    )


def grep_paths_and_recursive_flag(args: list[str]) -> tuple[list[str], bool]:
    paths: list[str] = []
    recursive = False
    pattern_seen = False
    after_double_dash = False
    index = 0

    while index < len(args):
        token = args[index]

        if after_double_dash:
            if pattern_seen:
                paths.append(token)
            else:
                pattern_seen = True
            index += 1
            continue

        if token == "--":
            after_double_dash = True
            index += 1
            continue

        if token.startswith("-") and token != "-":
            next_token = args[index + 1] if index + 1 < len(args) else None
            if grep_option_is_recursive(token) or grep_option_value_is_recursive(token, next_token):
                recursive = True
            if grep_option_sets_pattern(token):
                pattern_seen = True
            if grep_option_consumes_next(token):
                index += 2
                continue
            index += 1
            continue

        if pattern_seen:
            paths.append(token)
        else:
            pattern_seen = True
        index += 1

    return paths, recursive


def is_broad_recursive_grep(command: str, cwd: str = "") -> bool:
    for args, frame_cwd, assignments in executable_frames(command, "grep", cwd):
        paths, recursive = grep_paths_and_recursive_flag(args)
        if recursive and any(is_broad_root(path, frame_cwd, assignments) for path in paths or ["."]):
            return True
    return False


RG_MAX_DEPTH_FLAGS = {"--max-depth", "--maxdepth"}


def rg_paths_and_max_depth(args: list[str]) -> tuple[list[str], bool]:
    paths: list[str] = []
    max_depth = False
    pattern_seen = False
    after_double_dash = False
    index = 0
    while index < len(args):
        token = args[index]
        if after_double_dash:
            if pattern_seen:
                paths.append(token)
            else:
                pattern_seen = True
            index += 1
            continue
        if token == "--":
            after_double_dash = True
            index += 1
            continue
        if token in RG_MAX_DEPTH_FLAGS:
            max_depth = True
            index += 2
            continue
        if token.startswith("--max-depth=") or token.startswith("--maxdepth="):
            max_depth = True
            index += 1
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        if pattern_seen:
            paths.append(token)
        else:
            pattern_seen = True
        index += 1
    return paths, max_depth


def is_broad_rg(command: str, cwd: str = "") -> bool:
    # Keeps its own loop rather than using executable_frames, because the
    # stdin carve-out below needs to know whether the segment is pipe-fed.
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    assignments = shell_assignments(tokens)
    effective_cwd = cwd
    for segment, reads_pipe in command_segments_with_stdin(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        executable = os.path.basename(segment[index])
        if executable == "cd" and len(segment) > index + 1:
            target = expand_shell_variables(segment[index + 1], assignments)
            if not UNRESOLVED_EXPANSION.search(target):
                effective_cwd = normalize_command_path(target, effective_cwd)
            continue
        if executable != "rg":
            continue
        paths, max_depth = rg_paths_and_max_depth(segment[index + 1 :])
        if max_depth:
            continue
        if any(is_broad_root(path, effective_cwd, assignments) for path in paths):
            return True
        # With no path operands rg reads stdin instead of walking the cwd, so a
        # piped rg never touches the filesystem. GNU grep -r does both, hence no
        # equivalent carve-out in is_broad_recursive_grep.
        if not paths and not reads_pipe and is_broad_root(".", effective_cwd, assignments):
            return True
    return False


def operand_paths(args: list[str]) -> list[str]:
    """Non-option operands, honouring `--`. Option values are not separated."""
    paths: list[str] = []
    after_double_dash = False
    for token in args:
        if after_double_dash:
            paths.append(token)
            continue
        if token == "--":
            after_double_dash = True
            continue
        if token.startswith("-") and token != "-":
            continue
        paths.append(token)
    return paths


def is_broad_du(command: str, cwd: str = "") -> bool:
    """`du` over a broad root. `--max-depth` only limits reporting, not the walk."""
    for args, frame_cwd, assignments in executable_frames(command, "du", cwd):
        if any(is_broad_root(path, frame_cwd, assignments) for path in operand_paths(args) or ["."]):
            return True
    return False


def ls_is_recursive(args: list[str]) -> bool:
    for token in args:
        if token == "--":
            break
        if token == "--recursive":
            return True
        if token.startswith("--") or not token.startswith("-") or token == "-":
            continue
        if "R" in token[1:]:
            return True
    return False


def is_broad_recursive_ls(command: str, cwd: str = "") -> bool:
    for args, frame_cwd, assignments in executable_frames(command, "ls", cwd):
        if not ls_is_recursive(args):
            continue
        if any(is_broad_root(path, frame_cwd, assignments) for path in operand_paths(args) or ["."]):
            return True
    return False


def segment_reads_only_stdin(segment: list[str], index: int, reads_pipe: bool) -> bool:
    """Whether a pipe-fed search segment consumes stdin instead of walking the tree.

    rg and grep fall back to stdin only when given no path operands; grep -r walks
    the tree as well, and find never looks at stdin at all.
    """
    if not reads_pipe:
        return False
    executable = os.path.basename(segment[index])
    args = segment[index + 1 :]
    if executable == "rg":
        paths, _ = rg_paths_and_max_depth(args)
        return not paths
    if executable == "grep":
        paths, recursive = grep_paths_and_recursive_flag(args)
        return not paths and not recursive
    return False


def uses_shell_read_or_search(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return bool(SHELL_READ_SEARCH.search(command))
    for segment, reads_pipe in command_segments_with_stdin(tokens):
        index = shell_executable_index(segment)
        if index is None or os.path.basename(segment[index]) not in SEARCH_EXECUTABLES:
            continue
        if not segment_reads_only_stdin(segment, index, reads_pipe):
            return True
    return False


# -- repo-scoped rules -------------------------------------------------------


def cwd_is_under_repo_root(cwd: str) -> bool:
    return any(path_is_or_under(cwd, root) for root in REPO_ROOTS)


def segment_starts_uv_run_python(segment: list[str], index: int) -> bool:
    return (
        index + 2 < len(segment)
        and segment[index] == "uv"
        and segment[index + 1] == "run"
        and os.path.basename(segment[index + 2]) in {"python", "python3"}
    )


def uses_standalone_python(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        if segment_starts_uv_run_python(segment, index):
            continue
        if os.path.basename(segment[index]) in {"python", "python3"}:
            return True
    return False


def mentions_lock_or_config(text: str) -> bool:
    return any(pattern.search(text) for pattern in LOCK_OR_CONFIG_PATTERNS)


def lock_or_config_command_is_notable(command: str, cwd: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return cwd_is_under_repo_root(cwd) and mentions_lock_or_config(command)

    effective_cwd = cwd
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        executable = segment[index]
        args = segment[index + 1 :]
        if executable == "cd" and args:
            effective_cwd = normalize_command_path(args[0], effective_cwd)
            continue
        if executable in {"pip", "npm"} and args and args[0] == "install" and cwd_is_under_repo_root(effective_cwd):
            return True
    return False


def git_worktree_args(segment: list[str], git_index: int, cwd: str) -> tuple[list[str], str] | None:
    if segment[git_index] != "git":
        return None

    effective_cwd = cwd
    index = git_index + 1
    while index < len(segment):
        token = segment[index]
        if token == "worktree":
            return segment[index + 1 :], effective_cwd
        if token == "-C" and index + 1 < len(segment):
            effective_cwd = normalize_command_path(segment[index + 1], effective_cwd)
            index += 2
            continue
        if token.startswith("-C") and token != "-C":
            effective_cwd = normalize_command_path(token[2:], effective_cwd)
            index += 1
            continue
        if token == "-c" and index + 1 < len(segment):
            index += 2
            continue
        break
    return None


def git_worktree_target_paths(args: list[str]) -> list[str]:
    if not args:
        return []
    subcommand = args[0]
    rest = args[1:]
    if subcommand in {"add", "move", "repair"}:
        paths: list[str] = []
        index = 0
        while index < len(rest):
            token = rest[index]
            if token == "--":
                paths.extend(rest[index + 1 : index + 2])
                break
            if token in {"-b", "-B", "--detach", "--orphan"}:
                index += 2 if token in {"-b", "-B", "--orphan"} else 1
                continue
            if token.startswith("-"):
                index += 1
                continue
            paths.append(token)
            break
        if subcommand == "move" and len(paths) == 1:
            for token in rest[index + 1 :]:
                if not token.startswith("-"):
                    paths.append(token)
                    break
        return paths
    if subcommand in {"remove", "prune", "lock", "unlock"}:
        return [token for token in rest if not token.startswith("-")][:1]
    return []


def creates_worktree_inside_repo(command: str, cwd: str = "") -> bool:
    tokens = shell_tokens(command)
    if tokens is None or not REPO_ROOTS:
        return False

    assignments = shell_assignments(tokens)
    for segment in command_segments(tokens):
        index = shell_executable_index(segment)
        if index is None:
            continue
        expanded_segment = [expand_shell_variables(token, assignments) for token in segment]
        worktree_command = git_worktree_args(expanded_segment, index, cwd)
        if worktree_command is None:
            continue
        args, effective_cwd = worktree_command
        for token in git_worktree_target_paths(args):
            # An unresolved $VAR or $(...) means the real destination is unknowable,
            # so judging it would deny correct commands. Fail open, as the hook does
            # everywhere else.
            if UNRESOLVED_EXPANSION.search(token) or UNRESOLVED_EXPANSION.search(effective_cwd):
                continue
            target = normalize_command_path(token, effective_cwd)
            if any(path_is_or_under(target, root) for root in REPO_ROOTS):
                return True
    return False


def check_mutating_file_tool(tool_input: dict[str, Any], cwd: str) -> Response | None:
    path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    normalized_path = normalize_command_path(path, cwd)
    target_is_in_repo = any(path_is_or_under(normalized_path, root) for root in REPO_ROOTS)
    if target_is_in_repo and mentions_lock_or_config(normalized_path):
        return allow_with_context(LOCK_OR_CONFIG_NUDGE)
    return None


# -- post_tool ---------------------------------------------------------------


def handle_post_tool(payload: Payload) -> Response | None:
    text = str(payload.get("tool_output_text") or "")
    redacted = redact_sensitive(text)
    if redacted != text:
        return {"decision": "deny", "reason": redacted}
    return None


def redact_sensitive(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


# -- doctor ------------------------------------------------------------------

VIBE_HOOKS_PATH = "~/.vibe/hooks.toml"
GATE_HOOK_SCRIPT = "ship_check_gate.py"
# Tool names the pre_tool match must cover, in each spelling a harness uses.
REQUIRED_HOOK_MATCHES = ("bash", "file_system.bash", "process_start", "process.start", "edit", "write_file")


def _loaded_hooks(path: str) -> list[dict[str, Any]]:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    hooks = data.get("hooks")
    return [hook for hook in hooks if isinstance(hook, dict)] if isinstance(hooks, list) else []


def _match_covers(pattern: str, names: tuple[str, ...]) -> list[str]:
    """Tool names a Vibe `match` fails to select. Vibe searches, not fullmatch."""
    if not pattern.startswith("re:"):
        return [name for name in names if name != pattern]
    try:
        compiled = re.compile(pattern[3:])
    except re.error:
        return list(names)
    return [name for name in names if not compiled.search(name)]


def run_doctor(hooks_path: str | None = None) -> int:
    """Verify this machine actually runs the guard. Non-zero means it does not."""
    path = os.path.expanduser(hooks_path or VIBE_HOOKS_PATH)
    problems: list[str] = []

    if not os.path.isfile(path):
        print(f"policy doctor: FAIL no Vibe hooks file at {path}", file=sys.stderr)
        print("  Append the entries from hooks.example.toml.", file=sys.stderr)
        return 1
    try:
        hooks = _loaded_hooks(path)
    except Exception as error:  # noqa: BLE001 - report, never crash
        print(f"policy doctor: FAIL cannot parse {path}: {error}", file=sys.stderr)
        return 1

    policy_hooks = [
        hook
        for hook in hooks
        if hook.get("type") == "pre_tool" and "policy.py" in str(hook.get("command", ""))
    ]
    if not policy_hooks:
        problems.append("no pre_tool hook runs hooks/policy.py")
    for hook in policy_hooks:
        name = hook.get("name", "<unnamed>")
        if hook.get("strict") is not True:
            problems.append(f"pre_tool hook {name!r} is not strict = true, so a guard failure allows the call")
        uncovered = _match_covers(str(hook.get("match", "")), REQUIRED_HOOK_MATCHES)
        if uncovered:
            problems.append(f"pre_tool hook {name!r} match misses: {', '.join(uncovered)}")

    # The ship-check gate is optional until its script is installed, but a
    # present script with no hook is a silent gap.
    gate_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), GATE_HOOK_SCRIPT)
    gate_hooks = [
        hook
        for hook in hooks
        if hook.get("type") == "pre_tool" and GATE_HOOK_SCRIPT in str(hook.get("command", ""))
    ]
    if os.path.isfile(gate_script):
        if not gate_hooks:
            problems.append(f"{GATE_HOOK_SCRIPT} is installed but no pre_tool hook runs it")
        for hook in gate_hooks:
            if hook.get("strict") is not True:
                problems.append(f"gate hook {hook.get('name', '<unnamed>')!r} is not strict = true")

    if problems:
        print(f"policy doctor: FAIL ({path})", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("  See hooks.example.toml for the expected entries.", file=sys.stderr)
        return 1
    print(f"policy doctor: OK ({len(policy_hooks)} policy hook(s), {len(gate_hooks)} gate hook(s)) in {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Read a payload on stdin, print a verdict, always exit 0.

    A crash here would surface as a hook failure. Under `strict = true` that
    denies, but with a Python traceback as the user-visible reason; under a
    non-strict hook it would allow. An explicit deny is clearer in both cases.
    """
    argv = sys.argv[1:] if argv is None else argv
    if "--doctor" in argv:
        rest = [token for token in argv if token != "--doctor"]
        return run_doctor(rest[0] if rest else None)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
        response = handle_payload(payload)
    except Exception as error:  # noqa: BLE001 - a guard must not crash open
        print(
            json.dumps(
                deny(
                    "Blocked: the policy guard could not read this tool call "
                    f"({type(error).__name__}: {error}). This is a bug in the hook or the payload; "
                    "the command was not checked, so it was not allowed."
                )
            )
        )
        return 0
    if response:
        print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
