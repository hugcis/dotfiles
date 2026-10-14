import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


def test_quoted_off_overrides_a_slot_bound_thinking():
    config = _config({"subagents": {"scout": {"slot": "primary", "thinking": "off"}}})

    overrides = render.pi_managed_settings(config, PROFILE)["subagents"]["agentOverrides"]
    assert overrides["scout"] == {"model": "prov-a/big", "thinking": "off"}


def test_bare_yaml_off_is_rejected_with_a_quoting_hint():
    entry = yaml.safe_load("{slot: primary, thinking: off}")
    config = _config({"subagents": {"scout": entry}})

    with pytest.raises(render.ConfigError, match=r"models\.subagents\.scout.*quote"):
        render.pi_managed_settings(config, PROFILE)


def test_default_model_rejects_thinking():
    config = _config({"default": {"slot": "primary", "thinking": "low"}})

    with pytest.raises(render.ConfigError, match="defaultThinkingLevel"):
        render.pi_managed_settings(config, PROFILE)


def test_provider_name_keeps_the_agent_error_wording():
    with pytest.raises(render.ConfigError, match=r"provider_names\.pi\.mistral is missing \(needed by agent 'x'\)"):
        render.provider_name(
            {"provider_names": {"pi": {}}}, "pi", "mistral", "agent 'x'"
        )


PI_YAML = "settings:\n  theme: dark\nmodels:\n  default: primary\n"


def _stack(tmp_path, monkeypatch, pi_yaml: str, extensions=()) -> Path:
    stack = tmp_path / "stack"
    stack.mkdir()
    for name in extensions:
        (stack / "pi" / "extensions" / name).mkdir(parents=True)
    (stack / "pi.yaml").write_text(pi_yaml)
    shutil.copy(STACK / "methodologies.yaml", stack / "methodologies.yaml")
    # render loads methodology.py from STACK, which the sandbox lacks: cache the real one.
    render._load_methodology()
    monkeypatch.setattr(render, "STACK", stack)
    monkeypatch.setattr(render, "PI_HOME", tmp_path / "home")
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    return stack


def _settings_file(tmp_path, content) -> Path:
    path = tmp_path / "home/.pi/agent/settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def test_build_pi_is_none_without_pi_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "STACK", tmp_path)
    assert render.build_pi(PROFILE) is None


def test_build_pi_keeps_keys_render_does_not_own(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, PI_YAML)
    _settings_file(
        tmp_path,
        {"lastChangelogVersion": "1.1.0", "theme": "light", "packages": ["npm:x"]},
    )

    plan = render.build_pi(PROFILE)

    assert plan.settings == {
        "lastChangelogVersion": "1.1.0",
        "theme": "dark",
        "packages": ["npm:x"],
        "defaultProvider": "prov-a",
        "defaultModel": "big",
    }


def test_build_pi_plans_no_write_when_settings_are_current(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, PI_YAML)
    _settings_file(
        tmp_path, {"theme": "dark", "defaultProvider": "prov-a", "defaultModel": "big"}
    )

    assert render.build_pi(PROFILE).settings is None


def test_build_pi_rejects_unreadable_settings(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, PI_YAML)
    _settings_file(tmp_path, "{not json")

    with pytest.raises(render.ConfigError, match="settings.json"):
        render.build_pi(PROFILE)


def test_write_pi_settings_backs_up_the_previous_file(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, PI_YAML)
    path = _settings_file(tmp_path, '{"theme": "light"}')

    render.write_pi_settings(path, {"theme": "dark"})

    assert json.loads(path.read_text()) == {"theme": "dark"}
    backups = list((tmp_path / "backups").glob("pi-settings.pre-render-*/settings.json"))
    assert [b.read_text() for b in backups] == ['{"theme": "light"}']


def test_link_pi_extensions_links_moves_aside_and_prunes(tmp_path, monkeypatch):
    stack = _stack(
        tmp_path, monkeypatch, "", extensions=("comment-discipline", "subagent", "retired")
    )
    directory = tmp_path / "home/.pi/agent/extensions"
    (directory / "subagent").mkdir(parents=True)
    (directory / "subagent/config.json").write_text("{}")
    (directory / "retired").symlink_to(stack / "pi/extensions/retired")
    (directory / "host-local").mkdir()
    foreign = directory / "zellij"
    foreign.symlink_to(tmp_path)

    report = render.link_pi_extensions(["comment-discipline", "subagent"], directory)

    for name in ("comment-discipline", "subagent"):
        assert Path(os.readlink(directory / name)) == stack / "pi/extensions" / name
    assert not (directory / "retired").is_symlink()
    assert (directory / "host-local").is_dir()
    assert foreign.is_symlink()
    moved = list(
        (tmp_path / "backups").glob("pi-extensions.pre-render-*/subagent/config.json")
    )
    assert len(moved) == 1
    assert any("moved existing extension subagent" in line for line in report)


def test_link_pi_extensions_is_quiet_once_linked(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "", extensions=("subagent",))
    directory = tmp_path / "home/.pi/agent/extensions"

    render.link_pi_extensions(["subagent"], directory)

    assert render.link_pi_extensions(["subagent"], directory) == []


class Runner:
    def __init__(self, returncode: int = 0, stderr: str = ""):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.returncode, "", self.stderr)


def _pi_on_path(_name):
    return "/bin/pi"


def test_install_skips_packages_pi_already_has(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "")
    checkout = tmp_path / "ask-user-worktree"
    checkout.mkdir()
    (checkout / "package.json").write_text(json.dumps({"name": "pi-ask-user"}))
    _settings_file(tmp_path, {"packages": ["npm:pi-blackhole@0.5.11", str(checkout)]})
    runner = Runner()

    report = render.install_pi_packages(
        ["npm:pi-blackhole", "npm:pi-ask-user"], runner=runner, which=_pi_on_path
    )

    assert report == []
    assert runner.calls == []


def test_install_runs_pi_install_for_missing_packages(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "")
    _settings_file(tmp_path, {"packages": []})
    runner = Runner()

    report = render.install_pi_packages(["npm:pi-zentui"], runner=runner, which=_pi_on_path)

    assert runner.calls == [["pi", "install", "npm:pi-zentui"]]
    assert report == ["pi: installed npm:pi-zentui"]


def test_install_without_pi_on_path_prints_the_commands(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "")
    runner = Runner()

    report = render.install_pi_packages(
        ["npm:pi-zentui"], runner=runner, which=lambda _name: None
    )

    assert "not on PATH" in report[0]
    assert report[-1] == "  pi install npm:pi-zentui"
    assert runner.calls == []


def test_install_failure_is_reported_not_raised(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "")
    runner = Runner(returncode=1, stderr="npm ERR! 404\n")

    report = render.install_pi_packages(["npm:nope"], runner=runner, which=_pi_on_path)

    assert report == ["pi: `pi install npm:nope` failed: npm ERR! 404"]
