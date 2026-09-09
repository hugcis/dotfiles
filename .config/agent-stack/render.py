#!/usr/bin/env python3
"""Render agent definitions for pi, opencode, vibe, and Claude Code.

Reads a public roster.yaml plus an untracked per-machine profile.yaml and emits
native config for each harness. Slots absent from the profile emit no agent.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path

import yaml

STACK = Path(__file__).resolve().parent
SHELL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# The global software-engineering methodology. Exactly one of these supplies the
# methodology-specific half of AGENTS.md; the profile picks it, and an absent
# key keeps pre-migration profiles on superpowers.
METHODOLOGY_FRAGMENTS = {
    "superpowers": "10-superpowers.md",
    "compound-engineering": "10-compound-engineering.md",
}
# The mapping above is the only list of legal methodology names; adding a
# methodology means adding its fragment, so the two can never drift apart.
METHODOLOGIES = frozenset(METHODOLOGY_FRAGMENTS)


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
    # Optional: the vibe [[models]] alias to select for this slot. Vibe stores
    # `thinking` on the model alias, not on the agent, so an agent can only pick
    # a reasoning level by naming an alias that already carries it. Falls back to
    # `model` when the profile does not set it.
    vibe_model: str | None = None


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
                    vibe_model=binding.get("vibe_model"),
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
    # pi selects a reasoning level with a `:<level>` suffix on the model ref
    # (`pi --model <provider>/<model>:high`). pi-subagents' own `thinking:`
    # frontmatter key is documented as producing exactly this suffix ("Appended
    # as a `:level` suffix at runtime unless a suffix is already present"), so
    # the suffix is the primitive both routes converge on.
    model = model_ref(agent, profile, "pi")
    if agent.thinking:
        model = f"{model}:{agent.thinking}"
    turn_budget = (
        'turnBudget: {"maxTurns":12,"graceTurns":2}\n'
        if agent.role == "reviewer"
        else ""
    )
    content = f"""---
name: {agent.name}
description: {agent.role.capitalize()} agent on the {agent.slot} model slot.
model: {model}
tools: {tools}
acceptanceRole: {agent.acceptance}
{turn_budget}systemPromptMode: replace
inheritProjectContext: true
---

{agent.prompt}
"""
    return f"{agent.name}.md", content


def emit_opencode(agent: Agent, profile: dict) -> tuple[str, str]:
    # opencode expresses reasoning effort as a model `variant`: the provider
    # table in opencode.jsonc declares `variants: {high: {options: {reasoningEffort:
    # ...}}}` per model, and an agent picks one with a `variant:` frontmatter key.
    # Verified with `opencode debug agent <name>`, which echoes the resolved
    # "variant" field back for an agent file that sets it.
    variant = f"variant: {agent.thinking}\n" if agent.thinking else ""
    content = f"""---
description: {agent.role.capitalize()} agent on the {agent.slot} model slot.
mode: subagent
model: {model_ref(agent, profile, "opencode")}
{variant}permission:
  edit: {agent.write}
  bash: {agent.bash}
---

{agent.prompt}
"""
    return f"{agent.name}.md", content


def emit_vibe(agent: Agent) -> tuple[str, str]:
    perm = "never" if agent.write == "deny" else "always"
    safety = "safe" if agent.write == "deny" else "destructive"
    prompt_ids = {"coder": "opencode-coder", "reviewer": "opencode-reviewer"}
    title = agent.name.replace("-", " ").title()
    lines = [
        f'display_name = "{title}"',
        f'description = "{agent.role.capitalize()} agent on the {agent.slot} slot."',
        f'safety = "{safety}"',
        'agent_type = "subagent"',
        # Vibe has no per-agent thinking level: `thinking` is a property of the
        # [[models]] entry, and `active_model` is looked up by that entry's alias
        # (vibe 2.21.0 vibe_schema.py:352 `self.models.get(self.active_model)`,
        # with `models` keyed by alias). A slot therefore expresses a reasoning
        # level by naming an alias that carries it, via the optional profile key
        # `vibe_model`; without it we fall back to the bare model id.
        f'active_model = "{agent.vibe_model or agent.model}"',
        f'system_prompt_id = "{prompt_ids[agent.role]}"',
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
    # Claude Code takes a per-agent reasoning level as `effort`. Verified against
    # the installed Claude Code 2.1.220 binary: the strict agent frontmatter
    # schema declares `effort` ("Thinking effort: low, medium, high, max, or an
    # integer"), the agent-file parser validates it against
    # ["low","medium","high","xhigh","max"] (warning "Agent file ... has invalid
    # effort" otherwise) and carries it onto the resolved agent. A profile
    # `thinking` outside that set is passed through and Claude will warn.
    effort = f"effort: {agent.thinking}\n" if agent.thinking else ""
    content = f"""---
name: {agent.name}
description: {agent.role.capitalize()} agent on the {agent.slot} model slot.
model: {agent.model}
{effort}tools: {tools}
---

{agent.prompt}
"""
    return f"{agent.name}.md", content

TARGETS = {
    "pi": Path.home() / ".pi/agent/agents",
    "opencode": Path.home() / ".config/opencode/agent",
    "vibe": Path.home() / ".vibe/agents",
    "claude": Path.home() / ".claude/agents",
}

AGENTS_MD_TARGETS = [
    # ~/.pi/agent/AGENTS.md is a SYMLINK to ~/.vibe/AGENTS.md, so these four
    # paths are only three distinct files. distinct_agents_md_targets() collapses
    # the alias; ~/.pi/agent/prompts and ~/.pi/agent/skills are the same pattern.
    Path.home() / ".pi/agent/AGENTS.md",
    Path.home() / ".vibe/AGENTS.md",
    Path.home() / ".config/opencode/AGENTS.md",
    Path.home() / ".claude/CLAUDE.md",
]

# Skill directories that are allowed to contain third-party skills, but not
# personal skills that shadow agent-stack's canonical names.
DEFAULT_EXTERNAL_SKILL_DIRS = [Path.home() / ".agents/skills"]

# Where pre-render copies of clobbered AGENTS.md files go. Outside every harness
# directory so no harness ever loads a backup as a live config.
BACKUP_ROOT = Path.home() / ".local/state/agent-stack"


def distinct_agents_md_targets(targets: list[Path] | None = None) -> list[Path]:
    """Resolve AGENTS.md targets and drop aliases of the same file.

    Path.write_text follows symlinks, so writing both ends of an alias writes the
    same file twice and reports a count nobody can act on. Resolving first makes
    the write honest and lets the caller report the real number of files touched.
    """
    distinct: dict[Path, Path] = {}
    for target in (AGENTS_MD_TARGETS if targets is None else targets):
        distinct.setdefault(target.resolve(), target.resolve())
    return list(distinct.values())


def _backup_name(path: Path) -> str:
    """A collision-free flat filename for a backup of `path`.

    Two AGENTS.md targets share a basename, so the backup name has to carry the
    directory too.
    """
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        relative = Path(*path.parts[1:]) if path.is_absolute() else path
    return str(relative).replace("/", "__")


def backup_agents_md(targets: list[Path], content: str) -> list[str]:
    """Copy every target that differs from `content` into one backup directory.

    These files are untracked, so git holds no copy: an unconditional overwrite
    destroys hand-written content irrecoverably, and a new machine's own
    CLAUDE.md is exactly the case that matters. One backup directory per render,
    created with mkdtemp for the same collision safety prune_stale relies on.
    """
    doomed = [t for t in targets if t.is_file() and t.read_text() != content]
    if not doomed:
        return []
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="agents-md.pre-render-", dir=BACKUP_ROOT))
    for target in doomed:
        destination = backup / _backup_name(target)
        if destination.exists():
            raise FileExistsError(
                f"refusing to overwrite existing backup file {destination} "
                f"while backing up {target}"
            )
        shutil.copy2(target, destination)
    return [str(backup / _backup_name(t)) for t in doomed]


def _fragment_path(name: str) -> Path:
    fragments = (STACK / "agents.md.d").resolve()
    if not isinstance(name, str):
        raise ConfigError(
            f"profile.yaml: AGENTS.md fragment name must be a string; got {name!r}"
        )
    path = (fragments / name).resolve()
    try:
        path.relative_to(fragments)
    except ValueError:
        raise ConfigError(
            f"profile.yaml: AGENTS.md fragment '{name}' must stay within {fragments}."
        ) from None
    if not path.is_file():
        raise ConfigError(
            f"profile.yaml: AGENTS.md fragment '{name}' not found in {fragments}. "
            f"Fix agents_md_extra or add the fragment."
        )
    return path


def _read_fragment(name: str) -> str:
    """Read one agents.md.d fragment, or fail with a ConfigError naming it."""
    return _fragment_path(name).read_text().strip()


def methodology_name(profile: dict) -> str:
    name = profile.get("methodology", "superpowers")
    # A YAML list or dict is unhashable, so the membership test below would blow
    # up with a TypeError instead of the profile error a human can act on.
    if not isinstance(name, str) or name not in METHODOLOGIES:
        raise ConfigError(
            "profile.yaml: methodology must be one of "
            f"{', '.join(sorted(METHODOLOGIES))}; got {name!r}"
        )
    return name


def compose_agents_md(profile: dict) -> str:
    selected = methodology_name(profile)
    parts = [
        _read_fragment("00-universal.md"),
        _read_fragment(METHODOLOGY_FRAGMENTS[selected]),
    ]
    methodology_paths = {
        _fragment_path(name) for name in METHODOLOGY_FRAGMENTS.values()
    }
    for name in profile.get("agents_md_extra") or []:
        path = _fragment_path(name)
        if path in methodology_paths:
            raise ConfigError(
                f"profile.yaml: agents_md_extra must not list the methodology "
                f"fragment '{name}'. Set methodology: <name> instead; "
                f"this profile selects {selected!r}."
            )
        parts.append(path.read_text().strip())
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


def skill_names(directory: Path) -> set[str]:
    """Return skill entry names from `directory`.

    Skill entries are directories, including symlinks that resolve to
    directories. A missing directory means that harness has no skills installed
    at that surface yet, not that doctor should fail.
    """
    if not directory.is_dir():
        return set()
    return {path.name for path in directory.iterdir() if path.is_dir()}


def _load_methodology():
    """Load methodology.py by path, so the manifest has a single definition.

    Imported lazily and only by doctor: methodology.py loads this module in
    turn, and nothing here may depend on it at import time.
    """
    name = "agent_stack_methodology"
    if name in sys.modules:
        return sys.modules[name]
    loader = SourceFileLoader(name, str(STACK / "methodology.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


def active_skill_names(*, stack: Path, profile: Path, home: Path) -> set[str]:
    """Names published by the always-on local and selected methodology layers."""
    methodology = _load_methodology()
    controller = methodology.Controller(home=home, stack=stack, profile=profile)
    try:
        return set(controller.active_skills(controller.selected_methodology()))
    except methodology.MethodologyError as error:
        raise ConfigError(str(error)) from error


def external_skill_collisions(
    canonical: set[str],
    external_skill_dirs: list[Path],
) -> dict[Path, set[str]]:
    """Find third-party skill names that shadow canonical agent-stack skills."""
    collisions: dict[Path, set[str]] = {}
    for directory in external_skill_dirs:
        overlap = canonical & skill_names(directory)
        if overlap:
            collisions[directory] = overlap
    return collisions


def doctor(
    *,
    stack: Path = STACK,
    external_skill_dirs: list[Path] | None = None,
    canonical_skill_names: set[str] | None = None,
) -> list[str]:
    """Run read-only consistency checks for the rendered agent stack.

    Option B policy: agent-stack owns personal skills; external skill surfaces
    such as ~/.agents/skills may contain third-party skills only when their names
    do not collide with agent-stack skills.
    """
    if external_skill_dirs is None:
        external_skill_dirs = DEFAULT_EXTERNAL_SKILL_DIRS
    if canonical_skill_names is None:
        canonical_skill_names = skill_names(stack / "skills") | skill_names(
            stack / "local-skills"
        )
    collisions = external_skill_collisions(canonical_skill_names, external_skill_dirs)
    if collisions:
        lines = [
            "External skill name collision(s) detected.",
            "agent-stack is the source of truth for personal skills; external skill dirs may only contain non-overlapping third-party skills.",
        ]
        for directory, names in sorted(collisions.items(), key=lambda item: str(item[0])):
            lines.append(f"- {directory}: {', '.join(sorted(names))}")
        raise ConfigError("\n".join(lines))
    return []


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


def build_all(
    roster: dict, profile: dict
) -> tuple[list[Agent], dict[str, dict[str, str]], str, str]:
    agents = resolve_agents(roster, profile)
    planned: dict[str, dict[str, str]] = {h: {} for h in TARGETS}
    for agent in agents:
        for harness, emitter in (("pi", emit_pi), ("opencode", emit_opencode)):
            fname, content = emitter(agent, profile)
            planned[harness][fname] = content
        for harness, emitter in (("claude", emit_claude), ("vibe", emit_vibe)):
            fname, content = emitter(agent)
            planned[harness][fname] = content
    return agents, planned, compose_agents_md(profile), render_profile_env(profile)


def write_all(roster: dict, profile: dict) -> None:
    """Render every harness after building and validating every output."""
    agents, planned, agents_md, profile_env = build_all(roster, profile)

    # Phase 2: write.
    for harness, directory in TARGETS.items():
        directory.mkdir(parents=True, exist_ok=True)
        for fname, content in planned[harness].items():
            (directory / fname).write_text(content)
    agents_md_targets = distinct_agents_md_targets()
    saved = backup_agents_md(agents_md_targets, agents_md)
    for path in saved:
        print(f"backed up existing AGENTS.md to {path}")
    for target in agents_md_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(agents_md)
    (STACK / "profile.env").write_text(profile_env)

    # Phase 3: prune.
    for harness, directory in TARGETS.items():
        moved = prune_stale(directory, set(planned[harness]))
        if moved:
            print(f"{harness}: moved {len(moved)} stale file(s) aside: {', '.join(sorted(moved))}")

    print(f"rendered {len(agents)} agents to {len(TARGETS)} harnesses")
    print(
        f"wrote AGENTS.md to {len(agents_md_targets)} distinct file(s) "
        f"from {len(AGENTS_MD_TARGETS)} configured path(s)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("render", "validate", "doctor"),
                        default="render")
    parser.add_argument("--profile", type=Path,
                        default=STACK / "profile.yaml")
    parser.add_argument("--external-skill-dir", action="append", type=Path,
                        help="External third-party skill directory to check for name collisions. Repeatable; defaults to ~/.agents/skills.")
    parser.add_argument("--home", type=Path, default=Path.home(),
                        help="Home directory used to resolve the active methodology. Defaults to $HOME.")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            canonical = active_skill_names(
                stack=STACK, profile=args.profile, home=args.home
            )
            for message in doctor(
                stack=STACK,
                external_skill_dirs=(
                    args.external_skill_dir or [args.home / ".agents/skills"]
                ),
                canonical_skill_names=canonical,
            ):
                print(message)
            print("agent-stack doctor: ok")
            return
        roster = load_roster(STACK / "roster.yaml")
        profile = load_profile(args.profile)
        if args.command == "validate":
            build_all(roster, profile)
            print("agent-stack render validation: ok")
            return
        write_all(roster, profile)
    except ConfigError as exc:
        # Profile and doctor errors are written for a human on a new machine's
        # first run. SystemExit prints the message and exits 1 with no traceback.
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
