import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

STACK = Path(__file__).resolve().parents[1]

PROFILE = {
    "provider_names": {
        "pi": {"anthropic": "prov-a", "openai": "prov-o", "mistral": "prov-o"}
    },
    "slots": {
        "primary": {"provider": "anthropic", "model": "big", "thinking": "high"},
        "alt-low": {"provider": "openai", "model": "mid", "thinking": "low"},
        "fast": {"provider": "mistral", "model": "small"},
    },
}


def _config(models: dict, settings: dict | None = None) -> dict:
    return {
        "settings": settings or {},
        "models": models,
        "packages": [],
        "extensions": [],
    }


def test_load_pi_config_is_none_without_a_file(tmp_path):
    assert render.load_pi_config(tmp_path / "pi.yaml") is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("plugins: []\n", "unknown section"),
        ("settings:\n  defaultModel: x\n", "render derives"),
        ("extensions: [nowhere]\n", "nowhere"),
        ("models:\n  fallback: primary\n", "models takes only"),
        ("packages: npm:x\n", "list of strings"),
    ],
)
def test_load_pi_config_rejects_bad_shapes(tmp_path, monkeypatch, text, message):
    monkeypatch.setattr(render, "STACK", tmp_path)
    (tmp_path / "pi.yaml").write_text(text)

    with pytest.raises(render.ConfigError, match=message):
        render.load_pi_config(tmp_path / "pi.yaml")


def test_load_pi_config_accepts_an_extension_with_a_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "STACK", tmp_path)
    (tmp_path / "pi/extensions/subagent").mkdir(parents=True)
    (tmp_path / "pi.yaml").write_text("extensions: [subagent]\n")

    assert render.load_pi_config(tmp_path / "pi.yaml")["extensions"] == ["subagent"]


def test_managed_settings_resolve_slots_on_this_host():
    config = _config(
        {
            "default": "alt-low",
            "subagents": {
                "default": {"slot": "alt-low", "thinking": "medium"},
                "worker": "fast",
                "scout": {"slot": "alt-low"},
                "watchdog": "primary",
            },
        },
        settings={"theme": "dark"},
    )

    assert render.pi_managed_settings(config, PROFILE) == {
        "theme": "dark",
        "defaultProvider": "prov-o",
        "defaultModel": "mid",
        "subagents": {
            "defaultModel": "prov-o/mid",
            "defaultThinking": "medium",
            "agentOverrides": {
                "worker": {"model": "prov-o/small"},
                "scout": {"model": "prov-o/mid", "thinking": "low"},
            },
            "watchdog": {
                "main": {"model": "prov-a/big", "thinking": "high"},
                "children": {"model": "prov-a/big", "thinking": "high"},
            },
            "modelScope": {"enforce": True, "allow": ["prov-a/*", "prov-o/*"]},
        },
    }


def test_unbound_slot_names_the_slot_and_the_pi_yaml_entry():
    config = _config({"subagents": {"researcher": "research"}})

    with pytest.raises(
        render.ConfigError, match=r"slot 'research'.*models\.subagents\.researcher"
    ):
        render.pi_managed_settings(config, PROFILE)


def test_model_entry_rejects_unknown_keys():
    config = _config({"default": {"slot": "primary", "effort": "high"}})

    with pytest.raises(render.ConfigError, match="slot name or"):
        render.pi_managed_settings(config, PROFILE)


def test_provider_name_keeps_the_agent_error_wording():
    with pytest.raises(render.ConfigError, match=r"provider_names\.pi\.mistral is missing \(needed by agent 'x'\)"):
        render.provider_name(
            {"provider_names": {"pi": {}}}, "pi", "mistral", "agent 'x'"
        )
