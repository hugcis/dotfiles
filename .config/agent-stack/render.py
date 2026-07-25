#!/usr/bin/env python3
"""Render agent definitions for pi, opencode, vibe, and Claude Code.

Reads a public roster.yaml plus an untracked per-machine profile.yaml and emits
native config for each harness. Slots absent from the profile emit no agent.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

STACK = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")


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
        raise SystemExit(
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
            binding = slots.get(slot_name)
            if binding is None:
                continue  # slot unbound on this machine: emit nothing
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
