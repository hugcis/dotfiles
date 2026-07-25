#!/usr/bin/env python3
"""Render agent definitions for pi, opencode, vibe, and Claude Code.

Reads a public roster.yaml plus an untracked per-machine profile.yaml and emits
native config for each harness. Slots absent from the profile emit no agent.
"""
from __future__ import annotations

import argparse
import re
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

STACK = Path(__file__).resolve().parent
SHELL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ConfigError(ValueError):
    """Raised when roster.yaml or profile.yaml is invalid or incomplete."""


@dataclass
class Agent:
    name: str
    role: str
    slot: str
    provider: str
    model: str
    thinking: str | None
    write: str
    bash: str
    acceptance: str
    prompt: str


def load_roster(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def load_profile(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(
            f"No profile at {path}.\n"
            "Copy profile.example.yaml and fill in this machine's endpoints "
            "and slot bindings."
        )
    return yaml.safe_load(path.read_text())


def resolve_agents(roster: dict, profile: dict) -> list[Agent]:
    slots = profile.get("slots") or {}
    agents: list[Agent] = []
    for role_name, slot_names in roster["emit"].items():
        role = roster["roles"][role_name]
        prompt = (STACK / role["prompt"]).read_text().strip()
        for slot_name in slot_names:
            if slot_name not in slots:
                continue  # slot unbound on this machine: emit nothing
            binding = slots[slot_name] or {}
            for key in ("provider", "model"):
                if key not in binding:
                    raise ConfigError(
                        f"profile.yaml: slots.{slot_name}.{key} is missing "
                        f"(needed by role '{role_name}'). Add it to your machine profile."
                    )
            agents.append(
                Agent(
                    name=f"{role_name}-{slot_name}",
                    role=role_name,
                    slot=slot_name,
                    provider=binding["provider"],
                    model=binding["model"],
                    thinking=binding.get("thinking"),
                    write=role["write"],
                    bash=role["bash"],
                    acceptance=role["acceptance"],
                    prompt=prompt,
                )
            )
    return agents


def model_ref(agent: Agent, profile: dict, harness: str) -> str:
    if "provider_names" not in profile:
        raise ConfigError(
            f"profile.yaml: provider_names is missing "
            f"(needed by harness '{harness}' and agent '{agent.name}'). "
            f"Add it to your machine profile."
        )
    if harness not in profile["provider_names"]:
        raise ConfigError(
            f"profile.yaml: provider_names.{harness} is missing "
            f"(needed by agent '{agent.name}'). Add it to your machine profile."
        )
    if agent.provider not in profile["provider_names"][harness]:
        raise ConfigError(
            f"profile.yaml: provider_names.{harness}.{agent.provider} is missing "
            f"(needed by agent '{agent.name}'). Add it to your machine profile."
        )
    provider = profile["provider_names"][harness][agent.provider]
    return f"{provider}/{agent.model}"


def emit_pi(agent: Agent, profile: dict) -> tuple[str, str]:
    tools = "read, grep, find, ls, bash"
    if agent.write == "allow":
        tools += ", edit, write"
    content = f"""---
name: {agent.name}
description: {agent.role.capitalize()} agent on the {agent.slot} model slot.
model: {model_ref(agent, profile, "pi")}
tools: {tools}
acceptanceRole: {agent.acceptance}
systemPromptMode: replace
inheritProjectContext: true
---

{agent.prompt}
"""
    return f"{agent.name}.md", content


def emit_opencode(agent: Agent, profile: dict) -> tuple[str, str]:
    content = f"""---
description: {agent.role.capitalize()} agent on the {agent.slot} model slot.
mode: subagent
model: {model_ref(agent, profile, "opencode")}
permission:
  edit: {agent.write}
  bash: {agent.bash}
---

{agent.prompt}
"""
    return f"{agent.name}.md", content


def emit_vibe(agent: Agent) -> tuple[str, str]:
    perm = "never" if agent.write == "deny" else "always"
    safety = "safe" if agent.write == "deny" else "destructive"
    title = agent.name.replace("-", " ").title()
    lines = [
        f'display_name = "{title}"',
        f'description = "{agent.role.capitalize()} agent on the {agent.slot} slot."',
        f'safety = "{safety}"',
        'agent_type = "subagent"',
        f'active_model = "{agent.model}"',
        f'system_prompt_id = "{agent.role}"',
        "",
        "[tools.bash]",
        f'permission = "{agent.bash}"',
        "",
        "[tools.write_file]",
        f'permission = "{perm}"',
        "",
        "[tools.edit]",
        f'permission = "{perm}"',
        "",
        # Vibe's _migration.py maps legacy search_replace to edit; emit only
        # the current tool table so stale aliases do not come back.
    ]
    return f"{agent.name}.toml", "\n".join(lines)


def emit_claude(agent: Agent) -> tuple[str, str]:
    tools = "Read, Grep, Glob, Bash"
    if agent.write == "allow":
        tools += ", Edit, Write"
    content = f"""---
name: {agent.name}
description: {agent.role.capitalize()} agent on the {agent.slot} model slot.
model: {agent.model}
tools: {tools}
---

{agent.prompt}
"""
    return f"{agent.name}.md", content


# Future CLI main(): catch ConfigError and re-raise SystemExit(str(exc)) from exc.

TARGETS = {
    "pi": Path.home() / ".pi/agent/agents",
    "opencode": Path.home() / ".config/opencode/agent",
    "vibe": Path.home() / ".vibe/agents",
    "claude": Path.home() / ".claude/agents",
}

AGENTS_MD_TARGETS = [
    Path.home() / ".pi/agent/AGENTS.md",
    Path.home() / ".vibe/AGENTS.md",
    Path.home() / ".config/opencode/AGENTS.md",
    Path.home() / ".claude/CLAUDE.md",
]


def _read_fragment(name: str) -> str:
    """Read one agents.md.d fragment, or fail with a ConfigError naming it."""
    fragments = STACK / "agents.md.d"
    path = fragments / name
    if not path.is_file():
        raise ConfigError(
            f"profile.yaml: AGENTS.md fragment '{name}' not found in {fragments}. "
            f"Fix agents_md_extra or add the fragment."
        )
    return path.read_text().strip()


def compose_agents_md(profile: dict) -> str:
    parts = [_read_fragment("00-universal.md")]
    for name in profile.get("agents_md_extra") or []:
        parts.append(_read_fragment(name))
    return "\n\n".join(parts) + "\n"


def _shell_quote(value: object) -> str:
    """Quote a value for a shell file that gets sourced.

    shlex.quote leaves already-safe words bare; profile.env has always used an
    explicitly quoted `export X='...'` shape, so wrap those back up.
    """
    quoted = shlex.quote(str(value))
    if not quoted.startswith("'"):
        quoted = f"'{quoted}'"
    return quoted


def render_profile_env(profile: dict) -> str:
    ep = profile["endpoints"]
    lines = [
        "# Generated by render.py. Do not edit; do not commit.",
        "export CLAUDE_CODE_USE_FOUNDRY=1",
        f"export ANTHROPIC_FOUNDRY_BASE_URL={_shell_quote(ep['anthropic'])}",
        f"export AZURE_OPENAI_BASE_URL={_shell_quote(ep['openai'])}",
    ]
    for key, value in (profile.get("env") or {}).items():
        if not SHELL_IDENTIFIER.fullmatch(str(key)):
            raise ConfigError(
                f"profile.yaml: env key '{key}' is not a legal shell identifier "
                f"([A-Za-z_][A-Za-z0-9_]*). Rename it."
            )
        lines.append(f"export {key}={_shell_quote(value)}")
    return "\n".join(lines) + "\n"


def prune_stale(directory: Path, keep: set[str]) -> list[str]:
    """Move files this render did not produce into a fresh backup directory.

    Render targets are wholly owned by the renderer, so anything left over is a
    stale hand-written agent from before the migration. Files are moved rather
    than deleted: the previous roster is hand-authored work that is not in git.

    The backup directory is created with mkdtemp so two renders in the same
    second cannot land in the same place, and an existing destination file is
    never overwritten.
    """
    stale = [p for p in directory.iterdir() if p.is_file() and p.name not in keep]
    if not stale:
        return []
    backup = Path(tempfile.mkdtemp(
        prefix=f"{directory.name}.pre-render-", dir=directory.parent))
    for p in stale:
        destination = backup / p.name
        if destination.exists():
            raise FileExistsError(
                f"refusing to overwrite existing backup file {destination} "
                f"while moving {p} aside"
            )
        p.rename(destination)
    return [p.name for p in stale]


def write_all(roster: dict, profile: dict) -> None:
    """Render every harness in three strict phases.

    1. Resolve and build every output in memory. Any ConfigError surfaces here,
       before a single byte is written.
    2. Write the files.
    3. Prune stale files.

    This is not a transaction, but nothing on disk changes until every input
    has been validated, so a bad profile can no longer leave a half-updated
    roster across four live directories.
    """
    # Phase 1: build everything in memory.
    agents = resolve_agents(roster, profile)
    planned: dict[str, dict[str, str]] = {h: {} for h in TARGETS}
    for agent in agents:
        for harness, emitter in (("pi", emit_pi), ("opencode", emit_opencode)):
            fname, content = emitter(agent, profile)
            planned[harness][fname] = content
        for harness, emitter in (("claude", emit_claude), ("vibe", emit_vibe)):
            fname, content = emitter(agent)
            planned[harness][fname] = content
    agents_md = compose_agents_md(profile)
    profile_env = render_profile_env(profile)

    # Phase 2: write.
    for harness, directory in TARGETS.items():
        directory.mkdir(parents=True, exist_ok=True)
        for fname, content in planned[harness].items():
            (directory / fname).write_text(content)
    for target in AGENTS_MD_TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(agents_md)
    (STACK / "profile.env").write_text(profile_env)

    # Phase 3: prune.
    for harness, directory in TARGETS.items():
        moved = prune_stale(directory, set(planned[harness]))
        if moved:
            print(f"{harness}: moved {len(moved)} stale file(s) aside: {', '.join(sorted(moved))}")

    print(f"rendered {len(agents)} agents to {len(TARGETS)} harnesses")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path,
                        default=STACK / "profile.yaml")
    args = parser.parse_args()
    write_all(load_roster(STACK / "roster.yaml"), load_profile(args.profile))


if __name__ == "__main__":
    main()
