"""Isolated tests for the reversible methodology controller.

Every test builds a throwaway ``$HOME`` in ``tmp_path`` and injects it into the
controller, so no live harness directory (``~/.pi``, ``~/.claude``, ``~/.vibe``,
``~/.local``) is ever read or written. External commands go through an injected
runner: ``git`` and the artifact resolver run for real against temporary
repositories, and ``pi`` is emulated against a temporary settings file.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
import yaml


STACK_SOURCE = Path(__file__).resolve().parents[1]
CONTROLLER = STACK_SOURCE / "methodology.py"

SUPERPOWERS_SKILLS = ("brainstorming", "test-driven-development", "writing-plans")
CE_SKILLS = ("ce-brainstorm", "ce-plan", "ce-review")


def load_controller_module():
    loader = SourceFileLoader("methodology", str(CONTROLLER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module  # dataclasses needs the module registered
    loader.exec_module(module)
    return module


methodology = load_controller_module()


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=agent-stack tests",
            "-c",
            "user.email=tests@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def write_skill(root: Path, name: str) -> None:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(f"---\nname: {name}\n---\n\nbody\n")


def make_ce_upstream(
    path: Path,
    *,
    skills: tuple[str, ...] = CE_SKILLS,
    extension: bool = True,
    package: bool = True,
) -> str:
    """Create a local CE-shaped git repository and return its HEAD revision."""
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".", cwd=path)
    if package:
        (path / "package.json").write_text(
            json.dumps({"name": "compound-engineering-plugin"}) + "\n"
        )
    if extension:
        extensions = path / ".pi" / "extensions"
        extensions.mkdir(parents=True)
        (extensions / "compound-engineering.ts").write_text("export default {};\n")
    for name in skills:
        write_skill(path / "skills", name)
    git("add", "-A", cwd=path)
    git("commit", "-q", "-m", "ce", cwd=path)
    return git("rev-parse", "HEAD", cwd=path)


def commit_ce_revision(path: Path, *, skills: tuple[str, ...]) -> str:
    """Replace the upstream skill set and return the new revision."""
    shutil.rmtree(path / "skills")
    for name in skills:
        write_skill(path / "skills", name)
    git("add", "-A", cwd=path)
    git("commit", "-q", "--allow-empty", "-m", "ce update", cwd=path)
    return git("rev-parse", "HEAD", cwd=path)


class FakeRunner:
    """Record commands; run git/resolver for real and emulate ``pi``."""

    def __init__(self, home: Path):
        self.home = home
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self.settings_path = home / ".pi" / "agent" / "settings.json"

    @property
    def pi_calls(self) -> list[tuple[str, ...]]:
        return [args for args, _ in self.calls if args[0] == "pi"]

    def _packages(self) -> list[str]:
        if not self.settings_path.exists():
            return []
        return json.loads(self.settings_path.read_text()).get("packages", [])

    def _write_packages(self, packages: list[str]) -> None:
        settings = {}
        if self.settings_path.exists():
            settings = json.loads(self.settings_path.read_text())
        settings["packages"] = packages
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    def __call__(self, args, *, cwd=None, check=True, env=None):
        args = tuple(str(a) for a in args)
        self.calls.append((args, str(cwd) if cwd is not None else None))
        if args[0] == "pi":
            packages = self._packages()
            source = args[2]
            if args[1] == "install":
                if source not in packages:
                    packages.append(source)
            elif args[1] == "remove":
                packages = [p for p in packages if p != source]
            else:  # pragma: no cover - guard against silent API drift
                raise AssertionError(f"unexpected pi command {args}")
            self._write_packages(packages)
            return subprocess.CompletedProcess(list(args), 0, "", "")
        environment = os.environ.copy()
        environment["HOME"] = str(self.home)
        if env:
            environment.update(env)
        return subprocess.run(
            list(args),
            cwd=cwd,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        home: Path | None = None,
        expected_skill_count: int = len(CE_SKILLS),
        pi_extension: bool = True,
    ):
        self.tmp_path = tmp_path
        self.home = home if home is not None else tmp_path / "home"
        self.home.mkdir(parents=True)
        self.upstream = tmp_path / "upstream" / "compound-engineering-plugin"
        self.revision = make_ce_upstream(self.upstream, extension=pi_extension)
        self.stack = self.home / ".config" / "agent-stack"
        self._build_stack(expected_skill_count)
        self.runner = FakeRunner(self.home)
        self.controller = methodology.Controller(
            home=self.home, stack=self.stack, runner=self.runner
        )

    # -- construction ------------------------------------------------------

    def _build_stack(self, expected_skill_count: int) -> None:
        skills = self.stack / "skills"
        for name in SUPERPOWERS_SKILLS:
            write_skill(skills, name)
        fragments = self.stack / "agents.md.d"
        fragments.mkdir(parents=True)
        for name in (
            "00-universal.md",
            "10-superpowers.md",
            "10-compound-engineering.md",
        ):
            shutil.copy2(STACK_SOURCE / "agents.md.d" / name, fragments / name)
        binaries = self.stack / "bin"
        binaries.mkdir()
        shutil.copy2(
            STACK_SOURCE / "bin" / "ce-artifact-root", binaries / "ce-artifact-root"
        )
        (binaries / "ce-artifact-root").chmod(0o755)
        self.manifest_path = self.stack / "methodologies.yaml"
        self.manifest_path.write_text(
            "version: 1\n"
            "methodologies:\n"
            "  superpowers:\n"
            "    skills_path: skills\n"
            "  compound-engineering:\n"
            f"    repository: {self.upstream}\n"
            f"    revision: {self.revision}\n"
            "    checkout: ~/.local/share/agent-stack/compound-engineering-plugin\n"
            f"    expected_skill_count: {expected_skill_count}\n"
            "    pi_companions:\n"
            "      - npm:pi-subagents\n"
            "      - npm:pi-ask-user\n"
        )
        self.profile_path = self.stack / "profile.yaml"
        self.write_profile("superpowers")

    # -- helpers -----------------------------------------------------------

    def write_profile(self, name: str) -> Path:
        self.profile_path.write_text(f"methodology: {name}\n")
        return self.profile_path

    @property
    def checkout(self) -> Path:
        return self.home / ".local/share/agent-stack/compound-engineering-plugin"

    @property
    def state_path(self) -> Path:
        return self.home / ".local/state/agent-stack/methodology.json"

    @property
    def migrations(self) -> Path:
        return self.home / ".local/state/agent-stack/migrations"

    def migration_dirs(self) -> list[Path]:
        if not self.migrations.is_dir():
            return []
        return sorted(p for p in self.migrations.iterdir() if p.is_dir())

    def dest(self, harness: str) -> Path:
        return {
            "pi": self.home / ".pi/agent/skills",
            "claude": self.home / ".claude/skills",
            "vibe": self.home / ".vibe/skills",
        }[harness]

    def entries(self, harness: str) -> set[str]:
        directory = self.dest(harness)
        if not directory.is_dir():
            return set()
        return {p.name for p in directory.iterdir()}

    def link_fingerprint(self) -> dict[str, tuple[int, str]]:
        return {
            str(path): (path.lstat().st_ino, os.readlink(path))
            for name in ("pi", "claude", "vibe")
            if self.dest(name).is_dir()
            for path in self.dest(name).iterdir()
        }

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def write_pi_settings(self, packages: list[str]) -> Path:
        path = self.home / ".pi/agent/settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"packages": packages}, indent=2) + "\n")
        return path

    def write_instructions(self, name: str) -> list[Path]:
        universal = (self.stack / "agents.md.d/00-universal.md").read_text().strip()
        fragment = (
            (self.stack / f"agents.md.d/10-{name}.md").read_text().strip()
        )
        content = f"{universal}\n\n{fragment}\n"
        written = []
        for relative in (
            ".pi/agent/AGENTS.md",
            ".vibe/AGENTS.md",
            ".config/opencode/AGENTS.md",
            ".claude/CLAUDE.md",
        ):
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            written.append(path)
        return written

    def activate_superpowers(self) -> None:
        self.controller.activate("superpowers")

    def activate_ce(self, *, packages: list[str] | None = None) -> None:
        self.write_pi_settings(
            ["npm:pi-subagents"] if packages is None else packages
        )
        self.controller.prepare("compound-engineering")
        self.controller.activate("compound-engineering")


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def tree_fingerprint(root: Path) -> list[tuple[str, str]]:
    """Content fingerprint of a checkout, ignoring the ``.git`` directory."""
    entries = []
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        relative = str(path.relative_to(root))
        if path.is_symlink():
            entries.append((relative, "link:" + os.readlink(path)))
        elif path.is_dir():
            entries.append((relative, "dir"))
        else:
            entries.append((relative, path.read_text()))
    return entries


# --------------------------------------------------------------------------
# manifest, profile, and state schema
# --------------------------------------------------------------------------


def test_profile_methodology_absent_from_manifest_is_rejected(harness):
    harness.manifest_path.write_text(
        "version: 1\nmethodologies:\n  superpowers:\n    skills_path: skills\n"
    )
    harness.write_profile("compound-engineering")
    controller = methodology.Controller(
        home=harness.home, stack=harness.stack, runner=harness.runner
    )

    with pytest.raises(methodology.ConfigError) as error:
        controller.selected_methodology(harness.profile_path)

    assert "compound-engineering" in str(error.value)
    assert "methodologies.yaml" in str(error.value)


def test_manifest_error_names_the_missing_field_path(harness):
    manifest = yaml.safe_load(harness.manifest_path.read_text())
    del manifest["methodologies"]["compound-engineering"]["revision"]
    harness.manifest_path.write_text(yaml.safe_dump(manifest))

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_manifest(harness.manifest_path, home=harness.home)

    assert "methodologies.compound-engineering.revision" in str(error.value)


def test_manifest_rejects_malformed_skill_count(harness):
    manifest = yaml.safe_load(harness.manifest_path.read_text())
    manifest["methodologies"]["compound-engineering"]["expected_skill_count"] = "many"
    harness.manifest_path.write_text(yaml.safe_dump(manifest))

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_manifest(harness.manifest_path, home=harness.home)

    assert "methodologies.compound-engineering.expected_skill_count" in str(error.value)


def test_tracked_manifest_pins_the_reviewed_compound_engineering_source():
    manifest = methodology.load_manifest(
        STACK_SOURCE / "methodologies.yaml", home=Path("/nonexistent-home")
    )

    spec = manifest.compound_engineering
    assert spec.revision == "26bf5b1e377212c0e4996824fee1dea1eddd817d"
    assert spec.expected_skill_count == 33
    assert spec.pi_companions == ("npm:pi-subagents", "npm:pi-ask-user")
    assert spec.checkout == Path(
        "/nonexistent-home/.local/share/agent-stack/compound-engineering-plugin"
    )


def test_state_file_records_the_documented_schema(harness):
    harness.activate_ce()

    state = harness.state()

    assert state["version"] == 1
    assert state["active"] == "compound-engineering"
    assert state["ce_revision"] == harness.revision
    assert state["pi_ask_user_added"] is True
    assert sorted(state) == [
        "active",
        "ce_revision",
        "managed_links",
        "pi_ask_user_added",
        "version",
    ]
    assert all(link.startswith(str(harness.home)) for link in state["managed_links"])


# --------------------------------------------------------------------------
# prepare
# --------------------------------------------------------------------------


def test_prepare_clones_into_a_temporary_sibling_and_installs_atomically(harness):
    harness.controller.prepare("compound-engineering")

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert (harness.checkout / "package.json").is_file()
    clones = [
        args for args, _ in harness.runner.calls if args[:2] == ("git", "clone")
    ]
    assert len(clones) == 1
    destination = Path(clones[0][-1])
    assert destination.parent == harness.checkout.parent
    assert destination != harness.checkout
    leftovers = [
        p.name
        for p in harness.checkout.parent.iterdir()
        if p.name != harness.checkout.name
    ]
    assert leftovers == []


def test_prepare_rejects_a_checkout_whose_skill_count_differs(tmp_path):
    harness = Harness(tmp_path, expected_skill_count=33)

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert "33" in str(error.value)
    assert not harness.checkout.exists()


def test_prepare_rejects_a_checkout_missing_the_pi_extension(tmp_path):
    harness = Harness(tmp_path, pi_extension=False)

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert ".pi/extensions/compound-engineering.ts" in str(error.value)
    assert not harness.checkout.exists()


def test_failed_prepare_leaves_the_previous_checkout_active(harness):
    harness.controller.prepare("compound-engineering")
    before = tree_fingerprint(harness.checkout)
    broken = commit_ce_revision(harness.upstream, skills=("ce-plan",))

    with pytest.raises(methodology.MethodologyError):
        harness.controller.prepare("compound-engineering", revision=broken)

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert tree_fingerprint(harness.checkout) == before


def test_prepare_superpowers_validates_locally_without_network_commands(harness):
    harness.controller.prepare("superpowers")

    assert harness.runner.calls == []

    (harness.stack / "skills/brainstorming/SKILL.md").unlink()
    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("superpowers")
    assert "brainstorming" in str(error.value)


# --------------------------------------------------------------------------
# activation: links
# --------------------------------------------------------------------------


def test_ce_activation_removes_only_managed_superpowers_links(harness):
    harness.activate_superpowers()
    unrelated_target = harness.tmp_path / "elsewhere" / "external-skill"
    write_skill(unrelated_target.parent, "external-skill")
    for name in ("pi", "claude", "vibe"):
        (harness.dest(name) / "external-skill").symlink_to(unrelated_target)
        (harness.dest(name) / "hand-written").mkdir()
        (harness.dest(name) / "notes.md").write_text("mine\n")

    harness.activate_ce()

    for name in ("pi", "claude", "vibe"):
        entries = harness.entries(name)
        assert not entries & set(SUPERPOWERS_SKILLS)
        assert (harness.dest(name) / "hand-written").is_dir()
        assert not (harness.dest(name) / "hand-written").is_symlink()
        assert (harness.dest(name) / "notes.md").read_text() == "mine\n"
        link = harness.dest(name) / "external-skill"
        assert link.is_symlink()
        assert Path(os.readlink(link)) == unrelated_target


def test_ce_activation_links_every_ce_skill_into_claude_and_vibe(harness):
    harness.activate_ce()

    for name in ("claude", "vibe"):
        for skill in CE_SKILLS:
            link = harness.dest(name) / skill
            assert link.is_symlink()
            assert link.resolve() == (harness.checkout / "skills" / skill).resolve()
        assert harness.entries(name) >= set(CE_SKILLS)


def test_ce_activation_registers_the_pi_package_instead_of_pi_skill_links(harness):
    harness.activate_ce()

    assert harness.entries("pi") == set()
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert str(harness.checkout) in packages
    assert ("pi", "install", str(harness.checkout)) in harness.runner.pi_calls


def test_activation_stops_before_replacing_a_real_directory_collision(harness):
    harness.activate_superpowers()
    links_before = {
        name: sorted(harness.entries(name)) for name in ("pi", "claude", "vibe")
    }
    state_before = harness.state_path.read_bytes()
    snapshots_before = harness.migration_dirs()
    (harness.dest("claude") / "ce-plan").mkdir()
    (harness.dest("claude") / "ce-plan" / "SKILL.md").write_text("mine\n")

    with pytest.raises(methodology.MethodologyError) as error:
        harness.activate_ce()

    assert str(harness.dest("claude") / "ce-plan") in str(error.value)
    assert (harness.dest("claude") / "ce-plan" / "SKILL.md").read_text() == "mine\n"
    assert not (harness.dest("vibe") / "ce-review").exists()
    for name in ("pi", "claude", "vibe"):
        assert set(links_before[name]) <= harness.entries(name)
    assert harness.state_path.read_bytes() == state_before
    assert harness.migration_dirs() == snapshots_before


def test_activation_fails_closed_on_a_symlinked_skills_directory(harness):
    aliased = harness.home / ".vibe/skills"
    aliased.parent.mkdir(parents=True)
    other = harness.home / ".pi/agent/skills"
    other.mkdir(parents=True)
    aliased.symlink_to(other)

    with pytest.raises(methodology.MethodologyError) as error:
        harness.activate_superpowers()

    assert str(aliased) in str(error.value)
    assert aliased.is_symlink()
    assert harness.entries("pi") == set()


# --------------------------------------------------------------------------
# activation: packages, snapshots, rollback, idempotency
# --------------------------------------------------------------------------


def test_ce_activation_requires_pi_subagents_before_touching_anything(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-zentui"])
    harness.controller.prepare("compound-engineering")
    state_before = harness.state_path.read_bytes()
    snapshots_before = harness.migration_dirs()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert "npm:pi-subagents" in str(error.value)
    assert harness.entries("claude") == set(SUPERPOWERS_SKILLS)
    assert harness.runner.pi_calls == []
    assert harness.state_path.read_bytes() == state_before
    assert harness.migration_dirs() == snapshots_before


def test_snapshot_captures_settings_instructions_and_link_inventory(harness):
    harness.activate_superpowers()
    settings_before = harness.write_pi_settings(["npm:pi-subagents"]).read_text()
    harness.write_instructions("superpowers")
    snapshots_before = harness.migration_dirs()

    harness.controller.prepare("compound-engineering")
    harness.controller.activate("compound-engineering")

    migrations = [d for d in harness.migration_dirs() if d not in snapshots_before]
    assert len(migrations) == 1
    snapshot = migrations[0]
    assert snapshot.name.endswith("-superpowers-to-compound-engineering")
    assert json.loads((snapshot / "manifest.json").read_text())["version"] == 1
    assert (snapshot / "profile.yaml").read_text() == harness.profile_path.read_text()
    assert (snapshot / "pi-settings.json").read_text() == settings_before
    instructions = sorted(p.name for p in (snapshot / "instructions").iterdir())
    assert instructions == [
        ".claude__CLAUDE.md",
        ".config__opencode__AGENTS.md",
        ".pi__agent__AGENTS.md",
        ".vibe__AGENTS.md",
    ]
    inventory = json.loads((snapshot / "skill-links.json").read_text())
    claude = inventory[str(harness.dest("claude"))]
    assert sorted(claude) == sorted(SUPERPOWERS_SKILLS)
    assert claude["brainstorming"]["type"] == "symlink"
    assert claude["brainstorming"]["target"] == str(
        harness.stack / "skills" / "brainstorming"
    )


def test_returning_to_superpowers_restores_links_and_preserves_ce_checkout(harness):
    harness.activate_ce()
    checkout_before = tree_fingerprint(harness.checkout)

    harness.controller.activate("superpowers")

    for name in ("pi", "claude", "vibe"):
        assert harness.entries(name) == set(SUPERPOWERS_SKILLS)
        for skill in SUPERPOWERS_SKILLS:
            link = harness.dest(name) / skill
            assert link.is_symlink()
            assert link.resolve() == (harness.stack / "skills" / skill).resolve()
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert str(harness.checkout) not in packages
    assert ("pi", "remove", str(harness.checkout)) in harness.runner.pi_calls
    assert tree_fingerprint(harness.checkout) == checkout_before
    assert harness.state()["active"] == "superpowers"
    assert harness.state()["ce_revision"] is None


@pytest.mark.parametrize(
    "initial_packages, added, still_present_after_rollback",
    [
        (["npm:pi-subagents"], True, False),
        (["npm:pi-subagents", "npm:pi-ask-user"], False, True),
    ],
)
def test_pi_ask_user_is_removed_only_when_this_migration_added_it(
    harness, initial_packages, added, still_present_after_rollback
):
    harness.activate_ce(packages=list(initial_packages))
    assert harness.state()["pi_ask_user_added"] is added

    harness.controller.activate("superpowers")

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert ("npm:pi-ask-user" in packages) is still_present_after_rollback
    assert harness.state()["pi_ask_user_added"] is False


def test_second_identical_activation_changes_nothing(harness):
    harness.write_instructions("compound-engineering")
    harness.activate_ce()
    snapshots_before = harness.migration_dirs()
    state_before = (
        harness.state_path.read_bytes(),
        harness.state_path.stat().st_mtime_ns,
    )
    settings_before = harness.runner.settings_path.read_bytes()
    links_before = harness.link_fingerprint()
    harness.runner.calls.clear()

    harness.controller.activate("compound-engineering")

    assert harness.migration_dirs() == snapshots_before
    assert (
        harness.state_path.read_bytes(),
        harness.state_path.stat().st_mtime_ns,
    ) == state_before
    assert harness.runner.settings_path.read_bytes() == settings_before
    assert harness.runner.pi_calls == []
    assert harness.link_fingerprint() == links_before


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def failures(findings) -> list[str]:
    return [finding.check for finding in findings if finding.level == "error"]


def test_doctor_passes_on_a_freshly_activated_ce_stack(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert failures(findings) == []
    checks = {finding.check for finding in findings}
    assert {"vibe-discovery", "vibe-native-parity"} <= checks
    parity = [f for f in findings if f.check == "vibe-native-parity"]
    assert parity[0].level != "error"


def test_doctor_detects_instructions_that_do_not_match_the_methodology(harness):
    harness.activate_ce()
    harness.write_instructions("superpowers")

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "instructions" in failures(findings)


def test_doctor_detects_a_checkout_revision_that_differs_from_the_manifest(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    other = commit_ce_revision(harness.upstream, skills=CE_SKILLS)
    git("fetch", "-q", "origin", other, cwd=harness.checkout)
    git("checkout", "-q", "--detach", other, cwd=harness.checkout)

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "ce-revision" in failures(findings)


def test_doctor_detects_a_skill_count_that_differs_from_the_manifest(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    shutil.rmtree(harness.checkout / "skills" / "ce-review")

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "ce-skill-count" in failures(findings)


def test_doctor_detects_a_broken_managed_link(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    (harness.dest("claude") / "ce-plan").unlink()
    (harness.dest("claude") / "ce-plan").symlink_to(harness.tmp_path / "missing")

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "managed-link" in failures(findings)


def test_doctor_detects_a_link_pointing_at_the_inactive_source(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    (harness.dest("vibe") / "brainstorming").symlink_to(
        harness.stack / "skills" / "brainstorming"
    )

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "superpowers-discoverable" in failures(findings)


def test_doctor_detects_ce_links_left_behind_in_superpowers_mode(harness):
    harness.activate_ce()
    harness.controller.activate("superpowers")
    harness.write_instructions("superpowers")
    (harness.dest("claude") / "ce-plan").symlink_to(
        harness.checkout / "skills" / "ce-plan"
    )

    findings = harness.controller.doctor("superpowers", cwd=harness.tmp_path)

    assert "ce-discoverable" in failures(findings)


def test_doctor_detects_pi_companion_package_drift(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    harness.write_pi_settings([p for p in packages if p != "npm:pi-ask-user"])

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "pi-companions" in failures(findings)


def test_doctor_detects_an_artifact_root_inside_the_current_repository(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repository)
    # A home inside the repository forces ~/docs, and therefore the resolved
    # artifact root, below the repository the resolver is asked about.
    harness = Harness(tmp_path, home=repository / "home")
    harness.activate_ce()
    harness.write_instructions("compound-engineering")

    findings = harness.controller.doctor("compound-engineering", cwd=repository)

    assert "artifact-root" in failures(findings)


# --------------------------------------------------------------------------
# update
# --------------------------------------------------------------------------


def test_update_validates_the_candidate_before_moving_checkout_and_manifest(harness):
    harness.controller.prepare("compound-engineering")
    manifest_before = harness.manifest_path.read_text()
    candidate = commit_ce_revision(
        harness.upstream, skills=("ce-brainstorm", "ce-plan", "ce-ship")
    )

    messages = harness.controller.update(candidate)

    assert harness.manifest_path.read_text() == manifest_before.replace(
        harness.revision, candidate
    )
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == candidate
    assert (harness.checkout / "skills" / "ce-ship" / "SKILL.md").is_file()
    joined = "\n".join(messages)
    assert harness.revision in joined and candidate in joined


def test_failed_update_leaves_checkout_and_manifest_byte_identical(harness):
    harness.controller.prepare("compound-engineering")
    manifest_before = harness.manifest_path.read_bytes()
    checkout_before = tree_fingerprint(harness.checkout)
    candidate = commit_ce_revision(harness.upstream, skills=("ce-plan",))

    with pytest.raises(methodology.MethodologyError):
        harness.controller.update(candidate)

    assert harness.manifest_path.read_bytes() == manifest_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert tree_fingerprint(harness.checkout) == checkout_before


def test_failed_update_fetch_leaves_the_manifest_byte_identical(harness):
    harness.controller.prepare("compound-engineering")
    manifest_before = harness.manifest_path.read_bytes()

    with pytest.raises(methodology.MethodologyError):
        harness.controller.update("0" * 40)

    assert harness.manifest_path.read_bytes() == manifest_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------


def test_cli_doctor_runs_in_an_isolated_home(harness):
    harness.activate_superpowers()
    harness.write_instructions("superpowers")
    environment = os.environ.copy()
    environment["HOME"] = str(harness.home)

    result = subprocess.run(
        [
            "python3",
            str(CONTROLLER),
            "doctor",
            "--profile",
            str(harness.profile_path),
            "--stack",
            str(harness.stack),
            "--cwd",
            str(harness.tmp_path),
        ],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "superpowers" in result.stdout
