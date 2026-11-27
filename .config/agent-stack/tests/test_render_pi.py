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
from test_render import FIXTURE, _sandbox, _tree_contents

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
        ("packages: [npm:x, ./pi-ask-user]\n", r"package '\./pi-ask-user'.*npm:"),
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


def test_load_pi_config_reads_compact_at_tokens(tmp_path):
    (tmp_path / "pi.yaml").write_text("compactAtTokens: 500000\n")

    assert render.load_pi_config(tmp_path / "pi.yaml")["compactAtTokens"] == 500000


def test_load_pi_config_leaves_compact_at_tokens_unset_by_default(tmp_path):
    (tmp_path / "pi.yaml").write_text("settings:\n  theme: dark\n")

    assert render.load_pi_config(tmp_path / "pi.yaml")["compactAtTokens"] is None


@pytest.mark.parametrize("value", ["0", "-1", "'500000'", "true", "1.5"])
def test_load_pi_config_rejects_a_non_positive_int_compact_at_tokens(tmp_path, value):
    (tmp_path / "pi.yaml").write_text(f"compactAtTokens: {value}\n")

    with pytest.raises(render.ConfigError, match="compactAtTokens must be a positive integer"):
        render.load_pi_config(tmp_path / "pi.yaml")


def _models_json(*providers: tuple[str, list[dict]]) -> dict:
    return {"providers": {name: {"models": models} for name, models in providers}}


def test_compaction_overrides_cover_only_windows_above_the_threshold():
    models = _models_json(
        (
            "gw",
            [
                {"id": "above", "contextWindow": 1_000_000},
                {"id": "at", "contextWindow": 500_000},
                {"id": "below", "contextWindow": 200_000},
                {"id": "unknown"},
            ],
        )
    )

    assert render.pi_compaction_overrides(models, 500_000) == {
        "gw/above": {"reserveTokens": 500_000}
    }


def test_compaction_overrides_key_every_provider_by_provider_and_full_id():
    models = _models_json(
        ("gw", [{"id": "vendor/big", "contextWindow": 1_048_576}]),
        ("other", [{"id": "huge", "contextWindow": 2_000_000}]),
    )

    assert render.pi_compaction_overrides(models, 500_000) == {
        "gw/vendor/big": {"reserveTokens": 548_576},
        "other/huge": {"reserveTokens": 1_500_000},
    }


def test_compaction_overrides_never_shrink_the_ordinary_reserve():
    models = _models_json(("gw", [{"id": "barely", "contextWindow": 510_000}]))

    assert render.pi_compaction_overrides(models, 500_000, min_reserve=32_768) == {
        "gw/barely": {"reserveTokens": 32_768}
    }


def test_compaction_overrides_skip_malformed_entries():
    models = {
        "providers": {
            "broken": "not a provider",
            "gw": {"models": ["not a model", {"contextWindow": 1_000_000}, {"id": "ok", "contextWindow": 1_000_000}]},
        }
    }

    assert render.pi_compaction_overrides(models, 500_000) == {"gw/ok": {"reserveTokens": 500_000}}


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


def test_profile_pi_default_model_overrides_the_shared_default():
    """A host can pin its own Pi default model, through its own provider names."""
    profile = {**PROFILE, "pi_default_model": {"provider": "mistral", "model": "pinned"}}

    managed = render.pi_managed_settings(_config({"default": "primary"}), profile)

    assert (managed["defaultProvider"], managed["defaultModel"]) == ("prov-o", "pinned")


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param("fast", id="slot-name"),
        pytest.param({"model": "pinned"}, id="no-provider"),
        pytest.param({"provider": "mistral", "model": "pinned", "thinking": "low"}, id="extra-key"),
    ],
)
def test_profile_pi_default_model_must_name_a_provider_and_a_model(entry):
    profile = {**PROFILE, "pi_default_model": entry}

    with pytest.raises(render.ConfigError, match=r"pi_default_model"):
        render.pi_managed_settings(_config({"default": "primary"}), profile)


def test_provider_name_error_names_the_missing_key_and_its_consumer():
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
    monkeypatch.setattr(render, "STACK", stack)
    monkeypatch.setattr(render, "PI_HOME", tmp_path / "home")
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    # A real `pi` follows these, not PI_HOME; keep any stray call inside tmp_path.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "home/.pi/agent"))
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


COMPACT_PI_YAML = (
    "compactAtTokens: 500000\n"
    "settings:\n"
    "  compaction:\n"
    "    enabled: true\n"
    "    modelOverrides:\n"
    "      gw/big: {reserveTokens: 1}\n"
    "      gw/kept: {reserveTokens: 2}\n"
)


def _models_file(tmp_path, content) -> Path:
    path = tmp_path / "home/.pi/agent/models.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def test_build_pi_compacts_large_models_on_top_of_pi_yaml_compaction(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, COMPACT_PI_YAML)
    models = _models_file(
        tmp_path, _models_json(("gw", [{"id": "big", "contextWindow": 1_000_000}]))
    )
    models_before = models.read_text()

    plan = render.build_pi(PROFILE)

    assert plan.settings["compaction"] == {
        "enabled": True,
        "modelOverrides": {
            "gw/big": {"reserveTokens": 500_000},
            "gw/kept": {"reserveTokens": 2},
        },
    }
    assert models.read_text() == models_before


def test_build_pi_adds_no_overrides_without_models_json(tmp_path, monkeypatch):
    pi_yaml = "compactAtTokens: 500000\nsettings:\n  compaction: {enabled: true}\n"
    _stack(tmp_path, monkeypatch, pi_yaml)

    assert render.build_pi(PROFILE).settings == {"compaction": {"enabled": True}}


@pytest.mark.parametrize(
    ("content", "message"), [("{not json", "not valid JSON"), ("[]", "JSON object")]
)
def test_build_pi_rejects_an_unusable_models_json(tmp_path, monkeypatch, content, message):
    _stack(tmp_path, monkeypatch, COMPACT_PI_YAML)
    _models_file(tmp_path, content)

    with pytest.raises(render.ConfigError, match=rf"models\.json: .*{message}"):
        render.build_pi(PROFILE)


def test_write_pi_settings_backs_up_the_previous_file(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, PI_YAML)
    path = _settings_file(tmp_path, '{"theme": "light"}')

    backup = render.write_pi_settings(path, {"theme": "dark"})

    assert json.loads(path.read_text()) == {"theme": "dark"}
    backups = list((tmp_path / "backups").glob("pi-settings.pre-render-*/settings.json"))
    assert backups == [backup]
    assert backup.read_text() == '{"theme": "light"}'


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
    assert "pi: linked extension comment-discipline" in report
    assert "pi: linked extension subagent" in report
    assert "pi: removed extension link retired" in report


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


def test_install_reinstalls_a_pinned_package_registered_at_another_version(tmp_path, monkeypatch):
    # One host sat on pi-blackhole 0.5.7 for weeks while pi.yaml pinned 0.5.11.
    _stack(tmp_path, monkeypatch, "")
    _settings_file(tmp_path, {"packages": ["npm:pi-blackhole@0.5.7", "npm:pi-zentui"]})
    runner = Runner()

    report = render.install_pi_packages(
        ["npm:pi-blackhole@0.5.18", "npm:pi-zentui"], runner=runner, which=_pi_on_path
    )

    assert runner.calls == [["pi", "install", "npm:pi-blackhole@0.5.18"]]
    assert report == ["pi: installed npm:pi-blackhole@0.5.18"]


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


def test_install_reports_unreadable_settings_instead_of_raising(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "")
    _settings_file(tmp_path, "{not json")
    runner = Runner()

    report = render.install_pi_packages(["npm:x"], runner=runner, which=_pi_on_path)

    assert len(report) == 1
    assert report[0].startswith("pi: packages not checked:")
    assert runner.calls == []


def test_install_reports_a_runner_os_error_and_continues(tmp_path, monkeypatch):
    _stack(tmp_path, monkeypatch, "")
    calls: list[list[str]] = []

    def runner(args, **kwargs):
        calls.append(list(args))
        if args[-1] == "npm:first":
            raise FileNotFoundError("pi vanished")
        return subprocess.CompletedProcess(args, 0, "", "")

    report = render.install_pi_packages(
        ["npm:first", "npm:second"], runner=runner, which=_pi_on_path
    )

    assert report == [
        "pi: `pi install npm:first` failed: pi vanished",
        "pi: installed npm:second",
    ]
    assert calls[-1] == ["pi", "install", "npm:second"]


def test_write_all_applies_pi_yaml(tmp_path, monkeypatch, capsys):
    box = _sandbox(tmp_path, monkeypatch)
    (box["stack"] / "pi.yaml").write_text(PI_YAML)

    render.write_all(render.load_roster(STACK / "roster.yaml"), render.load_profile(FIXTURE))

    path = tmp_path / "home/.pi/agent/settings.json"
    assert json.loads(path.read_text()) == {
        "theme": "dark",
        "defaultProvider": "prov-anthropic",
        "defaultModel": "model-big",
    }
    assert f"pi: updated {path}" in capsys.readouterr().out.splitlines()


def test_write_all_adopts_a_host_with_an_existing_pi_setup(tmp_path, monkeypatch, capsys):
    box = _sandbox(tmp_path, monkeypatch)
    stack, home = box["stack"], box["home"]
    (stack / "pi/extensions/subagent").mkdir(parents=True)
    (stack / "pi.yaml").write_text(
        PI_YAML + "packages: [npm:pi-zentui, npm:pi-ask-user]\nextensions: [subagent]\n"
    )
    checkout = tmp_path / "ask-user-worktree"
    checkout.mkdir()
    (checkout / "package.json").write_text(json.dumps({"name": "pi-ask-user"}))
    settings_path = home / ".pi/agent/settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"lastChangelogVersion": "1.1.0", "packages": [str(checkout)]})
    )
    (home / ".pi/agent/extensions/subagent").mkdir(parents=True)
    (home / ".pi/agent/extensions/subagent/config.json").write_text("{}")
    calls: list[list[str]] = []

    def runner(args, **kwargs):
        # Stand in for `pi install`, which records the package in settings.json.
        calls.append(list(args))
        current = json.loads(settings_path.read_text())
        current["packages"].append(args[-1])
        settings_path.write_text(json.dumps(current))
        return subprocess.CompletedProcess(args, 0, "", "")

    roster, profile = render.load_roster(STACK / "roster.yaml"), render.load_profile(FIXTURE)

    render.write_all(roster, profile, runner=runner, which=_pi_on_path)

    assert json.loads(settings_path.read_text()) == {
        "lastChangelogVersion": "1.1.0",
        "packages": [str(checkout), "npm:pi-zentui"],
        "theme": "dark",
        "defaultProvider": "prov-anthropic",
        "defaultModel": "model-big",
    }
    link = home / ".pi/agent/extensions/subagent"
    assert Path(os.readlink(link)) == stack / "pi/extensions/subagent"
    moved = list(
        (tmp_path / "backups").glob("pi-extensions.pre-render-*/subagent/config.json")
    )
    assert len(moved) == 1
    assert calls == [["pi", "install", "npm:pi-zentui"]]
    backup = next((tmp_path / "backups").glob("pi-settings.pre-render-*/settings.json"))
    out = capsys.readouterr().out.splitlines()
    assert f"pi: updated {settings_path} (previous copy: {backup})" in out

    render.write_all(roster, profile, runner=runner, which=_pi_on_path)

    out = capsys.readouterr().out
    assert [line for line in out.splitlines() if line.startswith("pi:")] == []
    assert len(calls) == 1


def test_write_all_writes_nothing_when_pi_yaml_is_broken(tmp_path, monkeypatch):
    box = _sandbox(tmp_path, monkeypatch)
    (box["stack"] / "pi.yaml").write_text("models:\n  default: research\n")
    before = _tree_contents(tmp_path)

    with pytest.raises(render.ConfigError, match="research"):
        render.write_all(render.load_roster(STACK / "roster.yaml"), render.load_profile(FIXTURE))

    assert _tree_contents(tmp_path) == before


def test_validate_rejects_a_bad_pi_yaml_without_writing(tmp_path, monkeypatch):
    box = _sandbox(tmp_path, monkeypatch)
    shutil.copy(STACK / "roster.yaml", box["stack"] / "roster.yaml")
    profile = box["stack"] / "profile.yaml"
    shutil.copy(FIXTURE, profile)
    (box["stack"] / "pi.yaml").write_text("models:\n  default: research\n")
    before = _tree_contents(tmp_path)
    monkeypatch.setattr(sys, "argv", ["render.py", "validate", "--profile", str(profile)])

    with pytest.raises(SystemExit, match="research"):
        render.main()

    assert _tree_contents(tmp_path) == before


def _example_slots() -> list[str]:
    return list(render.load_profile(STACK / "profile.example.yaml")["slots"])


def _pi_yaml_slots(config: dict) -> list[str]:
    models = config["models"]
    entries = [models["default"], *models["subagents"].values()]
    return [e if isinstance(e, str) else e["slot"] for e in entries]


def test_public_pi_yaml_names_slots_not_models():
    config = render.load_pi_config(STACK / "pi.yaml")
    slots = _example_slots()

    assert all(slot in slots for slot in _pi_yaml_slots(config))
    assert all(p.startswith("npm:") for p in config["packages"])
    assert "/" not in json.dumps(config["settings"])


def test_public_pi_yaml_resolves_on_a_host_with_every_slot():
    profile = {
        "provider_names": {"pi": {"anthropic": "a", "openai": "o", "mistral": "m"}},
        "slots": {s: {"provider": "openai", "model": "x"} for s in _example_slots()},
    }

    managed = render.pi_managed_settings(render.load_pi_config(STACK / "pi.yaml"), profile)

    assert managed["subagents"]["agentOverrides"]["researcher"] == {"model": "o/x"}


GW = {"api": "openai-completions", "apiKey": "$EXAMPLE_KEY", "baseUrl": "https://gw.example/v1",
      "models": [{"id": "model-a", "contextWindow": 1_000_000}]}
OTHER = {"baseUrl": "https://other.example", "apiKey": "${OTHER_KEY}", "models": [{"id": "model-b"}]}


def _models_stack(tmp_path, monkeypatch, local: dict | None) -> Path:
    stack = _stack(tmp_path, monkeypatch, PI_YAML)
    if local is not None:
        (stack / render.PI_MODELS_LOCAL).write_text(json.dumps(local))
    return stack


def _host_file(tmp_path, providers: dict) -> Path:
    return _models_file(tmp_path, json.dumps({"providers": providers}, indent=2))


def test_pi_models_is_unmanaged_without_a_local_file(tmp_path, monkeypatch):
    _models_stack(tmp_path, monkeypatch, None)

    assert render.build_pi_models() is None


def test_pi_models_plans_no_write_when_the_provider_is_current(tmp_path, monkeypatch):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}})
    _host_file(tmp_path, {"other": OTHER, "gw": GW})

    assert render.build_pi_models().planned is None


def test_pi_models_adds_a_missing_provider_and_keeps_others_byte_identical(tmp_path, monkeypatch):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}})
    path = _host_file(tmp_path, {"other": OTHER})
    path.chmod(0o640)
    before = path.read_text()

    [line] = render.write_pi_models(render.build_pi_models())

    after = path.read_text()
    assert json.loads(after)["providers"] == {"other": OTHER, "gw": GW}
    # Everything up to the new provider is the old file, byte for byte.
    assert after.startswith(before[: before.rindex("}\n  }")])
    assert path.stat().st_mode & 0o777 == 0o640
    assert Path(line.split("previous copy: ")[1].rstrip(")")).read_text() == before
    assert render.build_pi_models().planned is None


def test_pi_models_replaces_in_place_and_removes_only_the_listed_providers(tmp_path, monkeypatch):
    local = {"providers": {"gw": GW}, "removeProviders": ["old", "absent"]}
    _models_stack(tmp_path, monkeypatch, local)
    _host_file(tmp_path, {"old": OTHER, "gw": {**GW, "models": []}, "other": OTHER})

    planned = json.loads(render.build_pi_models().planned)

    assert list(planned["providers"]) == ["gw", "other"]
    assert planned == {"providers": {"gw": GW, "other": OTHER}}


def test_pi_models_writes_a_missing_file(tmp_path, monkeypatch):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}})

    lines = render.write_pi_models(render.build_pi_models())

    path = tmp_path / "home/.pi/agent/models.json"
    assert json.loads(path.read_text()) == {"providers": {"gw": GW}}
    assert path.stat().st_mode & 0o777 == 0o600
    assert lines == [f"pi: updated {path}"]


@pytest.mark.parametrize("content", ["{not json", '{"providers": []}'])
def test_pi_models_rejects_an_unusable_file_and_leaves_it(tmp_path, monkeypatch, content):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}})
    path = _models_file(tmp_path, content)

    with pytest.raises(render.ConfigError, match=r"models\.json: "):
        render.build_pi_models()

    assert path.read_text() == content


def test_pi_models_leaves_a_symlinked_file_alone(tmp_path, monkeypatch):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}})
    target = tmp_path / "store-models.json"
    target.write_text("{}")
    link = tmp_path / "home/.pi/agent/models.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)

    with pytest.raises(render.ConfigError, match="symlink"):
        render.build_pi_models()


@pytest.mark.parametrize(
    "entry",
    [
        {**GW, "apiKey": "pasted-secret-value"},
        {**GW, "apiKey": "!cat ~/key"},
        {**GW, "apiKey": "prefix-$EXAMPLE_KEY"},
        {k: v for k, v in GW.items() if k != "apiKey"},
        {**GW, "headers": {"x-user": "pasted-secret-value"}},
    ],
)
def test_pi_models_rejects_anything_but_an_env_reference(tmp_path, monkeypatch, entry):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": entry}})

    with pytest.raises(render.ConfigError, match="environment reference") as error:
        render.build_pi_models()

    assert "pasted-secret" not in str(error.value)


@pytest.mark.parametrize(
    ("local", "message"),
    [
        ({"providers": {}}, "provider objects"),
        ({"providers": {"gw": {**GW, "headers": []}}}, "provider objects"),
        ({"providers": {"gw": GW}, "extra": 1}, "unknown key"),
        ({"providers": {"gw": GW}, "removeProviders": ["gw"]}, "both managed and removed"),
    ],
)
def test_pi_models_rejects_bad_local_shapes(tmp_path, monkeypatch, local, message):
    _models_stack(tmp_path, monkeypatch, local)

    with pytest.raises(render.ConfigError, match=message):
        render.build_pi_models()


def test_public_pi_models_example_loads():
    assert render.load_pi_models_local(STACK / "pi-models.local.example.json") is not None


def _pi_models_cli(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["render.py", "pi-models", *args])
    render.main()


def test_pi_models_check_prints_a_masked_diff_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}, "removeProviders": ["old"]})
    path = _host_file(tmp_path, {"old": {**OTHER, "apiKey": "pasted-secret-value"}})
    before = path.read_text()

    with pytest.raises(SystemExit) as exit_:
        _pi_models_cli(monkeypatch, "--check")

    out = capsys.readouterr().out
    assert exit_.value.code == 1
    assert '-      "apiKey": "<redacted>",' in out and '+      "apiKey": "$EXAMPLE_KEY",' in out
    assert "pasted-secret" not in out
    assert path.read_text() == before


def test_pi_models_check_reports_current_and_render_writes(tmp_path, monkeypatch, capsys):
    _models_stack(tmp_path, monkeypatch, {"providers": {"gw": GW}})
    path = _host_file(tmp_path, {"other": OTHER})

    _pi_models_cli(monkeypatch)
    _pi_models_cli(monkeypatch, "--check")

    assert capsys.readouterr().out.splitlines()[-1] == "pi models: current"
    assert json.loads(path.read_text())["providers"] == {"other": OTHER, "gw": GW}


def test_build_pi_compacts_models_from_the_planned_models_json(tmp_path, monkeypatch):
    stack = _stack(tmp_path, monkeypatch, "compactAtTokens: 500000\n")
    (stack / render.PI_MODELS_LOCAL).write_text(json.dumps({"providers": {"gw": GW}}))

    plan = render.build_pi(PROFILE, render.build_pi_models().models)

    assert plan.settings["compaction"]["modelOverrides"] == {"gw/model-a": {"reserveTokens": 500_000}}
