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
import re
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


# Mirrors the pinned upstream extension: only node built-ins, no dependency.
EXTENSION_SOURCE = (
    'import { dirname, resolve } from "node:path"\n'
    'import { fileURLToPath } from "node:url"\n'
    "export default function extension(pi: any) { return pi }\n"
)


def package_manifest(*, extra: dict | None = None) -> dict:
    """A package.json shaped like the pinned upstream one."""
    manifest = {
        "name": "compound-engineering-plugin",
        "pi": {
            "extensions": ["./.pi/extensions/compound-engineering.ts"],
            "skills": ["./skills"],
        },
    }
    if extra:
        manifest.update(extra)
    return manifest


def make_ce_upstream(
    path: Path,
    *,
    skills: tuple[str, ...] = CE_SKILLS,
    extension: bool = True,
    package: bool = True,
    package_extra: dict | None = None,
    extension_source: str | None = None,
    skill_body: str | None = None,
    extra_files: dict[str, str] | None = None,
) -> str:
    """Create a local CE-shaped git repository and return its HEAD revision."""
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".", cwd=path)
    if package:
        (path / "package.json").write_text(
            json.dumps(package_manifest(extra=package_extra)) + "\n"
        )
    if extension:
        extensions = path / ".pi" / "extensions"
        extensions.mkdir(parents=True)
        (extensions / "compound-engineering.ts").write_text(
            EXTENSION_SOURCE if extension_source is None else extension_source
        )
    for name in skills:
        write_skill(path / "skills", name)
        if skill_body is not None:
            (path / "skills" / name / "SKILL.md").write_text(skill_body)
    for relative, content in (extra_files or {}).items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
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


def pi_local_entry(home: Path, path: Path) -> str:
    """The string ``pi install <path>`` records in user settings.

    Confirmed against the installed pi sources
    (``dist/core/package-manager.js``: ``normalizePackageSourceForSettings``
    stores ``relative(agentDir, resolved)`` for local sources) and by an
    isolated ``pi install`` probe under a throwaway ``HOME``.
    """
    return os.path.relpath(path, home / ".pi" / "agent")


class FakeRunner:
    """Record commands; run git/resolver for real and emulate ``pi``.

    The ``pi`` emulation mirrors the real package manager: a local source is
    persisted relative to the agent directory, and install/remove match an
    existing entry by resolved path rather than by string equality.
    """

    NON_LOCAL_PREFIXES = ("npm:", "git:", "github:", "http:", "https:", "ssh:")
    NPM_SPEC = re.compile(r"^(@?[^@]+(?:/[^@]+)?)(?:@(.+))?$")

    def __init__(self, home: Path):
        self.home = home
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self.settings_path = home / ".pi" / "agent" / "settings.json"
        self.failing_pi_sources: set[str] = set()
        # Sources whose command writes settings and *then* exits nonzero, the
        # way a real `pi install` fails after persisting the new entry.
        self.mutating_pi_failures: set[str] = set()

    @property
    def pi_calls(self) -> list[tuple[str, ...]]:
        return [args for args, _ in self.calls if args[0] == "pi"]

    def _resolve(self, source: str) -> str | None:
        """Resolve a local package source the way pi does, or None if remote."""
        text = source.strip()
        if text.startswith(self.NON_LOCAL_PREFIXES):
            return None
        if text == "~":
            text = str(self.home)
        elif text.startswith("~/"):
            text = str(self.home / text[2:])
        if not os.path.isabs(text):
            text = os.path.join(str(self.settings_path.parent), text)
        return os.path.normpath(text)

    def _identity(self, source: str) -> str | None:
        """pi's npm package identity: `npm:<name>`, version stripped."""
        text = source.strip()
        if not text.startswith("npm:"):
            return None
        spec = text[len("npm:") :].strip()
        match = self.NPM_SPEC.match(spec)
        return "npm:" + (match.group(1) if match else spec)

    @staticmethod
    def _source_of(entry) -> str:
        """pi's ``getPackageSourceString``: strings and objects both allowed."""
        if isinstance(entry, dict):
            return str(entry.get("source", ""))
        return str(entry)

    def _matches(self, raw, source: str) -> bool:
        entry = self._source_of(raw)
        left, right = self._identity(entry), self._identity(source)
        if left is not None or right is not None:
            return left == right
        left, right = self._resolve(entry), self._resolve(source)
        if left is None or right is None:
            return entry.strip() == source.strip()
        return left == right

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
            if source in self.failing_pi_sources:
                raise subprocess.CalledProcessError(
                    1, list(args), "", f"pi: {args[1]} {source} failed\n"
                )
            if args[1] == "install":
                if not any(self._matches(p, source) for p in packages):
                    packages.append(
                        source
                        if self._resolve(source) is None
                        else pi_local_entry(self.home, Path(source))
                    )
            elif args[1] == "remove":
                packages = [p for p in packages if not self._matches(p, source)]
            else:  # pragma: no cover - guard against silent API drift
                raise AssertionError(f"unexpected pi command {args}")
            self._write_packages(packages)
            if source in self.mutating_pi_failures:
                raise subprocess.CalledProcessError(
                    1, list(args), "", f"pi: {args[1]} {source} failed after write\n"
                )
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
        **upstream_kwargs,
    ):
        self.tmp_path = tmp_path
        self.home = home if home is not None else tmp_path / "home"
        self.home.mkdir(parents=True)
        self.upstream = tmp_path / "upstream" / "compound-engineering-plugin"
        self.revision = make_ce_upstream(
            self.upstream, extension=pi_extension, **upstream_kwargs
        )
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

    def entry_fingerprint(self) -> dict[str, str]:
        """Every skill-destination entry, links and real entries alike."""
        fingerprint = {}
        for name in ("pi", "claude", "vibe"):
            directory = self.dest(name)
            if not directory.is_dir() or directory.is_symlink():
                continue
            for path in sorted(directory.iterdir()):
                if path.is_symlink():
                    fingerprint[str(path)] = "link:" + os.readlink(path)
                elif path.is_dir():
                    fingerprint[str(path)] = "dir"
                else:
                    fingerprint[str(path)] = "file:" + path.read_text()
        return fingerprint

    def baseline(self) -> dict:
        """Everything an activation is allowed to change, for no-op assertions."""
        return {
            "entries": self.entry_fingerprint(),
            "state": (
                self.state_path.read_bytes() if self.state_path.exists() else None
            ),
            "snapshots": self.migration_dirs(),
            "settings": (
                self.runner.settings_path.read_bytes()
                if self.runner.settings_path.exists()
                else None
            ),
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
    assert list(spec.pi_companions) == ["npm:pi-subagents", "npm:pi-ask-user"]
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


def test_prepare_refuses_a_checkout_path_holding_a_foreign_directory(harness):
    harness.checkout.mkdir(parents=True)
    (harness.checkout / "notes.md").write_text("someone else's work\n")

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert str(harness.checkout) in str(error.value)
    assert "git checkout" in str(error.value)
    assert (harness.checkout / "notes.md").read_text() == "someone else's work\n"


def test_prepare_refuses_a_checkout_of_another_repository(harness, tmp_path):
    other = tmp_path / "upstream" / "someone-elses-plugin"
    make_ce_upstream(other)
    harness.checkout.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "-q", str(other), str(harness.checkout), cwd=tmp_path)
    before = tree_fingerprint(harness.checkout)

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert str(other) in str(error.value)
    assert str(harness.upstream) in str(error.value)
    assert tree_fingerprint(harness.checkout) == before


def test_prepare_refuses_a_symlink_at_the_checkout_path(harness, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    harness.checkout.parent.mkdir(parents=True, exist_ok=True)
    harness.checkout.symlink_to(target)

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert str(harness.checkout) in str(error.value)
    assert harness.checkout.is_symlink()
    assert target.is_dir()


def test_prepare_replaces_a_checkout_this_controller_owns(harness):
    harness.controller.prepare("compound-engineering")
    shutil.rmtree(harness.checkout / "skills/ce-plan")

    harness.controller.prepare("compound-engineering")

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert (harness.checkout / "skills/ce-plan/SKILL.md").is_file()


# --------------------------------------------------------------------------
# prepare: runtime dependencies
# --------------------------------------------------------------------------


def test_prepare_rejects_an_extension_importing_a_third_party_module(tmp_path):
    harness = Harness(
        tmp_path,
        extension_source=(
            'import { defineCommand } from "citty"\n'
            "export default function extension(pi: any) { return pi }\n"
        ),
    )

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    message = str(error.value)
    assert "citty" in message
    assert "dependenc" in message
    assert not harness.checkout.exists()


def test_prepare_accepts_relative_imports_that_stay_inside_the_checkout(tmp_path):
    harness = Harness(
        tmp_path,
        extension_source=(
            'import { helper } from "./helper.ts"\n'
            'import { resolve } from "node:path"\n'
            "export default function extension(pi: any) { return pi }\n"
        ),
        extra_files={
            ".pi/extensions/helper.ts": (
                'import { sep } from "node:path"\nexport const helper = sep\n'
            )
        },
    )

    harness.controller.prepare("compound-engineering")

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision


def test_prepare_rejects_a_relative_import_that_does_not_resolve(tmp_path):
    harness = Harness(
        tmp_path,
        extension_source='import { helper } from "./missing.ts"\n',
    )

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert "./missing.ts" in str(error.value)
    assert not harness.checkout.exists()


def test_prepare_rejects_a_checkout_that_declares_no_pi_extension_entrypoint(
    tmp_path,
):
    harness = Harness(tmp_path, package_extra={"pi": {"skills": ["./skills"]}})

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert "pi.extensions" in str(error.value)
    assert not harness.checkout.exists()


def test_prepare_rejects_a_skill_that_invokes_the_package_cli(tmp_path):
    harness = Harness(
        tmp_path,
        package_extra={"scripts": {"convert": "bun run src/index.ts convert"}},
        skill_body="---\nname: ce-plan\n---\n\nRun `bun run src/index.ts convert`.\n",
        extra_files={"src/index.ts": "export default {}\n"},
    )

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    message = str(error.value)
    assert "src/index.ts" in message
    assert "dependenc" in message
    assert not harness.checkout.exists()


@pytest.mark.parametrize(
    "script_name, command, invocation",
    [
        ("convert", "bun run src/index.ts convert", "npm run convert"),
        ("convert", "bun run src/index.ts convert", "bun run convert"),
        ("convert", "bun run src/index.ts convert", "pnpm convert"),
        ("convert", "bun run src/index.ts convert", "pnpm run convert"),
        ("convert", "bun run src/index.ts convert", "yarn convert"),
        ("convert", "bun run src/index.ts convert", "yarn run convert"),
        ("plugin:validate", "eslint .", "npm run plugin:validate"),
        ("test", "vitest", "bun run test"),
    ],
)
def test_prepare_rejects_skills_invoking_dependency_bearing_package_scripts(
    tmp_path, script_name, command, invocation
):
    harness = Harness(
        tmp_path,
        package_extra={"scripts": {script_name: command}},
        skill_body=f"---\nname: ce-plan\n---\n\nRun `{invocation}`.\n",
        extra_files={"src/index.ts": "export default {}\n"},
    )

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.prepare("compound-engineering")

    assert script_name in str(error.value)
    assert "dependenc" in str(error.value)
    assert not harness.checkout.exists()


def test_prepare_ignores_ambiguous_project_lifecycle_script_invocations(tmp_path):
    harness = Harness(
        tmp_path,
        package_extra={"scripts": {"dev": "bun run src/index.ts"}},
        skill_body=(
            "---\nname: ce-plan\n---\n\n"
            "Start the user's project with `npm run dev`.\n"
        ),
        extra_files={"src/index.ts": "export default {}\n"},
    )

    harness.controller.prepare("compound-engineering")

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision


def test_failed_prepare_leaves_the_previous_checkout_active(harness):
    harness.controller.prepare("compound-engineering")
    before = tree_fingerprint(harness.checkout)
    broken = commit_ce_revision(harness.upstream, skills=("ce-plan",))

    with pytest.raises(methodology.MethodologyError):
        harness.controller.prepare("compound-engineering", revision=broken)

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert tree_fingerprint(harness.checkout) == before


def test_prepare_repairs_a_dirty_checkout_already_at_the_pinned_revision(harness):
    harness.controller.prepare("compound-engineering")
    clean = tree_fingerprint(harness.checkout)
    # Dirt that still validates: the skill count and the required files are
    # intact, only tracked content differs from the reviewed revision.
    (harness.checkout / "package.json").write_text(
        json.dumps(package_manifest(extra={"description": "tampered"})) + "\n"
    )
    (harness.checkout / "skills/ce-plan/SKILL.md").write_text("tampered\n")
    assert harness.controller._validate_checkout(harness.checkout, len(CE_SKILLS)) == []
    harness.runner.calls.clear()

    harness.controller.prepare("compound-engineering")

    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert git("status", "--porcelain", cwd=harness.checkout) == ""
    assert tree_fingerprint(harness.checkout) == clean
    clones = [
        args for args, _ in harness.runner.calls if args[:2] == ("git", "clone")
    ]
    assert len(clones) == 1


def test_prepare_leaves_a_clean_pinned_checkout_untouched(harness):
    harness.controller.prepare("compound-engineering")
    inode = harness.checkout.stat().st_ino
    harness.runner.calls.clear()

    harness.controller.prepare("compound-engineering")

    assert harness.checkout.stat().st_ino == inode
    assert [
        args for args, _ in harness.runner.calls if args[:2] == ("git", "clone")
    ] == []


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
    assert pi_local_entry(harness.home, harness.checkout) in packages
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


@pytest.mark.parametrize("outside", [False, True])
def test_activation_fails_closed_on_a_foreign_skills_directory_alias(
    tmp_path, harness, outside
):
    aliased = harness.home / ".vibe/skills"
    aliased.parent.mkdir(parents=True)
    other = tmp_path / "foreign-skills" if outside else harness.home / "skills-elsewhere"
    other.mkdir(parents=True)
    aliased.symlink_to(other)

    with pytest.raises(methodology.MethodologyError) as error:
        harness.activate_superpowers()

    assert str(aliased) in str(error.value)
    assert aliased.is_symlink()
    assert os.readlink(aliased) == str(other)
    assert harness.entries("pi") == set()


def test_activation_migrates_a_legacy_alias_between_skill_destinations(harness):
    """The stack used to ship ~/.pi/agent/skills as a link to ~/.vibe/skills."""
    vibe = harness.dest("vibe")
    vibe.mkdir(parents=True)
    alias = harness.dest("pi")
    alias.parent.mkdir(parents=True)
    alias.symlink_to(vibe)

    messages = harness.controller.activate("superpowers")

    assert not alias.is_symlink()
    assert alias.is_dir()
    assert alias.resolve() != vibe.resolve()
    for name in ("pi", "vibe"):
        assert harness.entries(name) == set(SUPERPOWERS_SKILLS)
        for skill in SUPERPOWERS_SKILLS:
            link = harness.dest(name) / skill
            assert link.is_symlink()
            assert link.resolve() == (harness.stack / "skills" / skill).resolve()
    assert any(str(alias) in message and str(vibe) in message for message in messages)


def test_a_failed_activation_restores_a_legacy_destination_alias(harness):
    vibe = harness.dest("vibe")
    vibe.mkdir(parents=True)
    alias = harness.dest("pi")
    alias.parent.mkdir(parents=True)
    alias.symlink_to(vibe)
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    harness.runner.failing_pi_sources.add(str(harness.checkout))

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    # the alias was migrated, then the *package* step failed: the rollback has
    # to put the exact symlink back, not merely refuse to start.
    assert "pi install" in str(error.value)
    assert "rollback was incomplete" not in str(error.value)
    assert alias.is_symlink()
    assert os.readlink(alias) == str(vibe)
    assert harness.entries("vibe") == set()


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
    assert pi_local_entry(harness.home, harness.checkout) not in packages
    assert str(harness.checkout) not in packages
    assert ("pi", "remove", str(harness.checkout)) in harness.runner.pi_calls
    assert tree_fingerprint(harness.checkout) == checkout_before
    assert harness.state()["active"] == "superpowers"
    assert harness.state()["ce_revision"] is None


@pytest.mark.parametrize(
    "initial_packages, added",
    [
        (["npm:pi-subagents"], True),
        (["npm:pi-subagents", "npm:pi-ask-user"], False),
    ],
)
def test_pi_ask_user_survives_a_rollback_as_an_independent_utility(
    harness, initial_packages, added
):
    harness.activate_ce(packages=list(initial_packages))
    assert harness.state()["pi_ask_user_added"] is added

    harness.controller.activate("superpowers")

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert "npm:pi-ask-user" in packages
    assert [
        call
        for call in harness.runner.pi_calls
        if call[1] == "remove" and "pi-ask-user" in call[2]
    ] == []
    # The record of who installed it survives; nothing removes it.
    assert harness.state()["pi_ask_user_added"] is added


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


def test_doctor_names_a_leftover_ce_pi_package_in_superpowers_mode(harness):
    harness.activate_ce()
    harness.controller.activate("superpowers")
    harness.write_instructions("superpowers")
    entry = pi_local_entry(harness.home, harness.checkout)
    harness.write_pi_settings(["npm:pi-subagents", entry])

    findings = harness.controller.doctor("superpowers", cwd=harness.tmp_path)

    assert "pi-package" in failures(findings)
    reported = [f for f in findings if f.check == "pi-package"]
    assert entry in reported[0].message


def test_doctor_passes_in_superpowers_mode_without_the_ce_pi_package(harness):
    harness.activate_ce()
    harness.controller.activate("superpowers")
    harness.write_instructions("superpowers")

    findings = harness.controller.doctor("superpowers", cwd=harness.tmp_path)

    assert failures(findings) == []


def test_doctor_detects_pi_companion_package_drift(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    harness.write_pi_settings([p for p in packages if p != "npm:pi-ask-user"])

    findings = harness.controller.doctor("compound-engineering", cwd=harness.tmp_path)

    assert "pi-companions" in failures(findings)


def test_doctor_names_an_external_skill_shadowing_an_active_ce_skill(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    external = harness.home / ".agents/skills"
    write_skill(external, "ce-plan")
    write_skill(external, "third-party-only")

    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )

    collisions = [f for f in findings if f.check == "external-skills"]
    assert len(collisions) == 1
    assert collisions[0].level == "error"
    assert "ce-plan" in collisions[0].message
    assert "third-party-only" not in collisions[0].message


def test_doctor_ignores_an_external_skill_named_after_the_inactive_methodology(
    harness,
):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    write_skill(harness.home / ".agents/skills", SUPERPOWERS_SKILLS[0])

    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )

    assert [f for f in findings if f.check == "external-skills"] == []


def test_doctor_names_an_external_skill_shadowing_an_active_superpowers_skill(
    harness,
):
    harness.activate_superpowers()
    harness.write_instructions("superpowers")
    write_skill(harness.home / ".agents/skills", SUPERPOWERS_SKILLS[0])

    findings = harness.controller.doctor("superpowers", cwd=harness.tmp_path)

    collisions = [f for f in findings if f.check == "external-skills"]
    assert len(collisions) == 1
    assert SUPERPOWERS_SKILLS[0] in collisions[0].message


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

    # A well-formed sha that no remote can serve: the fetch is what fails.
    with pytest.raises(methodology.MethodologyError):
        harness.controller.update("a" * 40)

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


# --------------------------------------------------------------------------
# strict state loading
# --------------------------------------------------------------------------


def valid_state(**overrides) -> dict:
    state = {
        "version": 1,
        "active": "superpowers",
        "ce_revision": None,
        "managed_links": [],
        "pi_ask_user_added": False,
    }
    state.update(overrides)
    return state


def write_state(harness, payload: dict) -> Path:
    harness.state_path.parent.mkdir(parents=True, exist_ok=True)
    harness.state_path.write_text(json.dumps(payload, indent=2) + "\n")
    return harness.state_path


@pytest.mark.parametrize(
    "missing",
    ["version", "active", "ce_revision", "managed_links", "pi_ask_user_added"],
)
def test_state_requires_every_schema_key(harness, missing):
    payload = valid_state()
    del payload[missing]
    path = write_state(harness, payload)

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_state(path)

    assert missing in str(error.value)
    assert str(path) in str(error.value)


def test_state_rejects_an_unknown_active_methodology(harness):
    path = write_state(harness, valid_state(active="vibe-coding"))

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_state(path)

    assert "active" in str(error.value)
    assert "vibe-coding" in str(error.value)


def test_state_requires_a_null_ce_revision_in_superpowers_mode(harness):
    path = write_state(harness, valid_state(ce_revision="a" * 40))

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_state(path)

    assert "ce_revision" in str(error.value)
    assert "superpowers" in str(error.value)


@pytest.mark.parametrize("revision", [None, "26bf5b1", "not-a-sha", 26])
def test_state_requires_a_full_sha_in_compound_engineering_mode(harness, revision):
    path = write_state(
        harness, valid_state(active="compound-engineering", ce_revision=revision)
    )

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_state(path)

    assert "ce_revision" in str(error.value)


def test_state_rejects_a_malformed_managed_link_entry(harness):
    path = write_state(harness, valid_state(managed_links=["/a", 7]))

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_state(path)

    assert "managed_links[1]" in str(error.value)


def test_state_written_by_activation_reloads_strictly(harness):
    harness.activate_ce()

    state = methodology.load_state(harness.state_path)

    assert state.active == "compound-engineering"
    assert state.ce_revision == harness.revision


# --------------------------------------------------------------------------
# activation preflight: pinned revision, clean checkout, destination topology
# --------------------------------------------------------------------------


def test_activation_requires_the_checkout_head_to_match_the_pinned_revision(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    drifted = commit_ce_revision(harness.upstream, skills=CE_SKILLS)
    git("fetch", "-q", "origin", drifted, cwd=harness.checkout)
    git("checkout", "-q", "--detach", drifted, cwd=harness.checkout)
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert drifted in str(error.value)
    assert harness.revision in str(error.value)
    assert harness.runner.pi_calls == []
    assert harness.baseline() == before


def test_activation_rejects_a_dirty_tracked_checkout(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    (harness.checkout / "skills" / "ce-plan" / "SKILL.md").write_text("edited\n")
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert str(harness.checkout) in str(error.value)
    assert "skills/ce-plan/SKILL.md" in str(error.value)
    assert harness.runner.pi_calls == []
    assert harness.baseline() == before


def test_activation_rejects_a_regular_file_skill_destination(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    shutil.rmtree(harness.dest("vibe"))
    harness.dest("vibe").write_text("not a directory\n")
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert str(harness.dest("vibe")) in str(error.value)
    assert harness.dest("vibe").read_text() == "not a directory\n"
    assert harness.runner.pi_calls == []
    assert harness.baseline() == before


def test_activation_rejects_a_skills_ancestor_symlinked_outside_home(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    outside = harness.tmp_path / "outside-home" / "vibe"
    (outside / "skills").mkdir(parents=True)
    shutil.rmtree(harness.home / ".vibe")
    (harness.home / ".vibe").symlink_to(outside)
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert str(harness.home / ".vibe") in str(error.value)
    assert str(outside) in str(error.value)
    assert list((outside / "skills").iterdir()) == []
    assert harness.runner.pi_calls == []
    assert harness.baseline() == before


def test_activation_allows_a_skills_ancestor_symlinked_inside_home(harness):
    inside = harness.home / "alternate-vibe"
    (inside / "skills").mkdir(parents=True)
    (harness.home / ".vibe").symlink_to(inside)

    harness.activate_superpowers()

    assert harness.entries("vibe") == set(SUPERPOWERS_SKILLS)


# --------------------------------------------------------------------------
# pi package recognition and rollback of external command failures
# --------------------------------------------------------------------------


def test_ce_package_recognition_matches_the_checkout_exactly(harness):
    controller = harness.controller
    checkout = harness.checkout
    relative = pi_local_entry(harness.home, checkout)
    tilde = "~/" + str(checkout.relative_to(harness.home))

    for entry in (str(checkout), relative, tilde, f"{checkout}/"):
        assert controller._ce_package_entry([entry]) == entry, entry
    for entry in (
        f"{checkout}/skills",
        f"{relative}/skills",
        str(checkout.parent),
        f"{checkout}-other",
        "npm:pi-subagents",
        "compound-engineering-plugin",
    ):
        assert controller._ce_package_entry([entry]) is None, entry


def test_ce_package_recognition_reads_object_entries(harness):
    entry = {"source": pi_local_entry(harness.home, harness.checkout)}

    assert harness.controller._pi_packages() == []
    harness.write_pi_settings([entry, "npm:pi-subagents"])

    packages = harness.controller._pi_packages()
    assert packages == [entry["source"], "npm:pi-subagents"]
    assert harness.controller._ce_package_entry(packages) == entry["source"]


def test_ce_package_removal_passes_the_absolute_checkout_path(harness):
    harness.activate_ce()
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert pi_local_entry(harness.home, harness.checkout) in packages

    harness.controller.activate("superpowers")

    removals = [c for c in harness.runner.pi_calls if c[1] == "remove"]
    assert ("pi", "remove", str(harness.checkout)) in removals
    remaining = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert harness.controller._ce_package_entry(remaining) is None


def test_a_descendant_package_entry_is_never_removed(harness):
    harness.activate_superpowers()
    descendant = str(harness.checkout / "skills")
    harness.write_pi_settings(["npm:pi-subagents", descendant])
    harness.controller.prepare("compound-engineering")

    harness.controller.activate("compound-engineering")
    activated = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert pi_local_entry(harness.home, harness.checkout) in activated
    harness.controller.activate("superpowers")

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert descendant in packages
    assert harness.controller._ce_package_entry(packages) is None


def test_a_failed_pi_command_rolls_back_links_packages_and_state(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    harness.runner.failing_pi_sources = {"npm:pi-ask-user"}
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert "npm:pi-ask-user" in str(error.value)
    assert harness.baseline() == before
    assert harness.state()["active"] == "superpowers"
    for name in ("pi", "claude", "vibe"):
        assert harness.entries(name) == set(SUPERPOWERS_SKILLS)
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert harness.controller._ce_package_entry(packages) is None


# --------------------------------------------------------------------------
# update transactionality
# --------------------------------------------------------------------------


def test_update_rejects_an_abbreviated_revision_before_touching_anything(harness):
    harness.controller.prepare("compound-engineering")
    manifest_before = harness.manifest_path.read_bytes()
    checkout_before = tree_fingerprint(harness.checkout)
    harness.runner.calls.clear()

    with pytest.raises(methodology.ConfigError) as error:
        harness.controller.update(harness.revision[:8])

    assert harness.revision[:8] in str(error.value)
    assert "40" in str(error.value)
    assert harness.runner.calls == []
    assert harness.manifest_path.read_bytes() == manifest_before
    assert tree_fingerprint(harness.checkout) == checkout_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision


def test_update_refuses_an_ambiguous_manifest_rewrite_before_any_mutation(harness):
    harness.controller.prepare("compound-engineering")
    harness.manifest_path.write_text(
        harness.manifest_path.read_text() + f"# pinned at {harness.revision}\n"
    )
    manifest_before = harness.manifest_path.read_bytes()
    checkout_before = tree_fingerprint(harness.checkout)
    candidate = commit_ce_revision(harness.upstream, skills=CE_SKILLS)
    harness.runner.calls.clear()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.update(candidate)

    assert str(harness.manifest_path) in str(error.value)
    assert harness.runner.calls == []
    assert harness.manifest_path.read_bytes() == manifest_before
    assert tree_fingerprint(harness.checkout) == checkout_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision


def test_update_rejects_a_candidate_manifest_that_fails_strict_reload(harness):
    """A rewrite that would produce an unloadable manifest never runs."""
    harness.controller.prepare("compound-engineering")
    text = harness.manifest_path.read_text().replace(
        "    expected_skill_count: 3\n", "    expected_skill_count: many\n"
    )
    harness.manifest_path.write_text(text)
    manifest_before = harness.manifest_path.read_bytes()
    checkout_before = tree_fingerprint(harness.checkout)
    candidate = commit_ce_revision(harness.upstream, skills=CE_SKILLS)

    with pytest.raises(methodology.ConfigError):
        harness.controller.update(candidate)

    assert harness.manifest_path.read_bytes() == manifest_before
    assert tree_fingerprint(harness.checkout) == checkout_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision


def test_failed_manifest_replacement_restores_the_previous_checkout(
    harness, monkeypatch
):
    harness.controller.prepare("compound-engineering")
    manifest_before = harness.manifest_path.read_bytes()
    checkout_before = tree_fingerprint(harness.checkout)
    candidate = commit_ce_revision(
        harness.upstream, skills=("ce-brainstorm", "ce-plan", "ce-ship")
    )
    original_write = methodology._write_atomically

    def failing_write(path, content):
        if Path(path) == harness.manifest_path:
            raise OSError(30, "Read-only file system")
        return original_write(path, content)

    monkeypatch.setattr(methodology, "_write_atomically", failing_write)

    with pytest.raises(OSError):
        harness.controller.update(candidate)

    monkeypatch.undo()
    assert harness.manifest_path.read_bytes() == manifest_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert tree_fingerprint(harness.checkout) == checkout_before
    assert not (harness.checkout / "skills" / "ce-ship").exists()
    leftovers = [
        p.name
        for p in harness.checkout.parent.iterdir()
        if p.name != harness.checkout.name
    ]
    assert leftovers == []


def test_failed_manifest_reload_restores_checkout_and_manifest(harness, monkeypatch):
    harness.controller.prepare("compound-engineering")
    manifest_before = harness.manifest_path.read_bytes()
    checkout_before = tree_fingerprint(harness.checkout)
    candidate = commit_ce_revision(
        harness.upstream, skills=("ce-brainstorm", "ce-plan", "ce-ship")
    )
    original_load = methodology.load_manifest

    def failing_load(path, *, home):
        if Path(path) == harness.manifest_path:
            raise methodology.ConfigError(f"{path}: injected reload failure")
        return original_load(path, home=home)

    monkeypatch.setattr(methodology, "load_manifest", failing_load)

    with pytest.raises(methodology.ConfigError):
        harness.controller.update(candidate)

    monkeypatch.undo()
    assert harness.manifest_path.read_bytes() == manifest_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert tree_fingerprint(harness.checkout) == checkout_before


def test_prepare_rejects_an_abbreviated_revision_override(harness):
    harness.controller.prepare("compound-engineering")
    harness.runner.calls.clear()

    with pytest.raises(methodology.ConfigError) as error:
        harness.controller.prepare("compound-engineering", revision="26bf5b1")

    assert "26bf5b1" in str(error.value)
    assert harness.runner.calls == []


# --------------------------------------------------------------------------
# pi package identity: versions, scopes, and manifest-declared companions
# --------------------------------------------------------------------------


def test_package_identity_ignores_the_version_and_keeps_the_scope():
    identity = methodology.package_identity

    assert identity("npm:pi-ask-user") == "npm:pi-ask-user"
    assert identity("npm:pi-ask-user@2.0.1") == "npm:pi-ask-user"
    assert identity("npm: pi-ask-user@^2.0 ") == "npm:pi-ask-user"
    assert identity("npm:@acme/pi-ask-user") == "npm:@acme/pi-ask-user"
    assert identity("npm:@acme/pi-ask-user@1.2.3-rc.1") == "npm:@acme/pi-ask-user"
    assert identity("/local/checkout") is None
    assert identity("git:example.com/pkg") is None


def test_a_versioned_companion_satisfies_the_manifest_prerequisite(harness):
    harness.activate_ce(packages=["npm:pi-subagents@1.4.0"])

    assert harness.state()["active"] == "compound-engineering"
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert "npm:pi-subagents@1.4.0" in packages
    assert "npm:pi-subagents" not in packages


def test_a_pinned_pre_existing_companion_is_never_rewritten_or_removed(harness):
    harness.activate_ce(packages=["npm:pi-subagents@1.4.0", "npm:pi-ask-user@2.0.1"])

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert "npm:pi-ask-user@2.0.1" in packages
    assert "npm:pi-ask-user" not in packages
    assert harness.state()["pi_ask_user_added"] is False

    harness.controller.activate("superpowers")

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert "npm:pi-ask-user@2.0.1" in packages
    assert [c for c in harness.runner.pi_calls if "pi-ask-user" in c[2]] == []


def rewrite_companions(harness, companions: str) -> "methodology.Controller":
    """Replace the manifest companion list and return a fresh controller."""
    text = harness.manifest_path.read_text()
    head, _, _ = text.partition("    pi_companions:\n")
    harness.manifest_path.write_text(head + "    pi_companions:\n" + companions)
    return methodology.Controller(
        home=harness.home, stack=harness.stack, runner=harness.runner
    )


def test_required_companions_come_from_the_manifest(harness):
    controller = rewrite_companions(
        harness,
        "      - npm:@acme/pi-guard\n      - npm:pi-ask-user\n",
    )
    harness.write_pi_settings(["npm:pi-subagents"])
    controller.prepare("compound-engineering")

    with pytest.raises(methodology.MethodologyError) as error:
        controller.activate("compound-engineering")

    assert "npm:@acme/pi-guard" in str(error.value)
    assert harness.runner.pi_calls == []

    harness.write_pi_settings(["npm:@acme/pi-guard@3.1.0"])
    controller.activate("compound-engineering")

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert "npm:@acme/pi-guard@3.1.0" in packages
    assert "npm:pi-ask-user" in packages
    assert harness.state()["pi_ask_user_added"] is True

    controller.activate("superpowers")

    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert "npm:@acme/pi-guard@3.1.0" in packages
    assert "npm:pi-ask-user" in packages


def test_manifest_rejects_a_companion_that_is_not_a_string(harness):
    text = harness.manifest_path.read_text()
    head, _, _ = text.partition("    pi_companions:\n")
    harness.manifest_path.write_text(
        head + "    pi_companions:\n      - source: npm:pi-subagents\n"
    )

    with pytest.raises(methodology.ConfigError) as error:
        methodology.load_manifest(harness.manifest_path, home=harness.home)

    assert "methodologies.compound-engineering.pi_companions[0]" in str(error.value)


def test_ce_package_recognition_accepts_a_file_url_entry(harness):
    controller = harness.controller
    checkout = harness.checkout

    for entry in (f"file://{checkout}", f"file://localhost{checkout}"):
        assert controller._ce_package_entry([entry]) == entry, entry
    for entry in (
        f"file://{checkout}/skills",
        f"file://elsewhere{checkout}",
        f"file://{checkout.parent}",
    ):
        assert controller._ce_package_entry([entry]) is None, entry


def test_superpowers_activates_when_the_manifest_declares_no_ce(harness):
    harness.manifest_path.write_text(
        "version: 1\nmethodologies:\n  superpowers:\n    skills_path: skills\n"
    )
    harness.write_pi_settings(["npm:pi-subagents"])
    controller = methodology.Controller(
        home=harness.home, stack=harness.stack, runner=harness.runner
    )

    controller.activate("superpowers")

    for name in ("pi", "claude", "vibe"):
        assert harness.entries(name) == set(SUPERPOWERS_SKILLS)
    assert harness.state()["active"] == "superpowers"
    assert harness.runner.pi_calls == []
    harness.write_instructions("superpowers")
    assert failures(controller.doctor("superpowers", cwd=harness.tmp_path)) == []


def test_a_pi_command_that_mutates_settings_then_fails_is_undone(harness):
    harness.activate_superpowers()
    harness.write_pi_settings(["npm:pi-subagents"])
    harness.controller.prepare("compound-engineering")
    harness.runner.mutating_pi_failures = {"npm:pi-ask-user"}
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.activate("compound-engineering")

    assert "npm:pi-ask-user" in str(error.value)
    packages = json.loads(harness.runner.settings_path.read_text())["packages"]
    assert packages == ["npm:pi-subagents"]
    assert harness.baseline() == before
    assert harness.state()["active"] == "superpowers"


def test_a_failed_activation_restores_the_pi_settings_file_byte_for_byte(harness):
    harness.activate_superpowers()
    # A hand-formatted settings file with an object entry, a sibling key, and a
    # deliberate package order: a rollback that replays `pi` commands cannot
    # reproduce any of it, only restoring the original bytes can.
    settings = harness.runner.settings_path
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "packages": [
                    {"source": "npm:pi-subagents", "enabled": True},
                    "npm:pi-other",
                ],
                "theme": "dark",
            },
            indent=4,
        )
        + "\n"
    )
    harness.controller.prepare("compound-engineering")
    harness.runner.failing_pi_sources = {"npm:pi-ask-user"}
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError):
        harness.controller.activate("compound-engineering")

    assert settings.read_bytes() == before["settings"]
    assert harness.baseline() == before


# --------------------------------------------------------------------------
# update while compound-engineering is active
# --------------------------------------------------------------------------


NEW_CE_SKILLS = ("ce-brainstorm", "ce-plan", "ce-ship")


def test_update_relinks_and_records_the_new_revision_while_ce_is_active(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    candidate = commit_ce_revision(harness.upstream, skills=NEW_CE_SKILLS)

    harness.controller.update(candidate)

    for name in ("claude", "vibe"):
        assert harness.entries(name) == set(NEW_CE_SKILLS)
        for skill in NEW_CE_SKILLS:
            link = harness.dest(name) / skill
            assert link.is_symlink()
            assert link.resolve() == (harness.checkout / "skills" / skill).resolve()
    state = harness.state()
    assert state["ce_revision"] == candidate
    assert sorted(state["managed_links"]) == sorted(
        str(harness.dest(name) / skill)
        for name in ("claude", "vibe")
        for skill in NEW_CE_SKILLS
    )
    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )
    assert failures(findings) == []


def test_a_same_revision_update_replaces_a_dirty_checkout(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    clean = tree_fingerprint(harness.checkout)
    manifest_before = harness.manifest_path.read_bytes()
    (harness.checkout / "skills/ce-plan/SKILL.md").write_text("tampered\n")

    harness.controller.update(harness.revision)

    assert tree_fingerprint(harness.checkout) == clean
    assert git("status", "--porcelain", cwd=harness.checkout) == ""
    assert harness.manifest_path.read_bytes() == manifest_before
    assert harness.state()["ce_revision"] == harness.revision
    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )
    assert failures(findings) == []


def test_a_failed_relink_during_update_restores_links_state_and_manifest(harness):
    harness.activate_ce()
    candidate = commit_ce_revision(harness.upstream, skills=NEW_CE_SKILLS)
    collision = harness.dest("vibe") / "ce-ship"
    collision.mkdir()
    (collision / "SKILL.md").write_text("hand written\n")
    manifest_before = harness.manifest_path.read_bytes()
    before = harness.baseline()

    with pytest.raises(methodology.MethodologyError) as error:
        harness.controller.update(candidate)

    assert "ce-ship" in str(error.value)
    assert harness.manifest_path.read_bytes() == manifest_before
    assert git("rev-parse", "HEAD", cwd=harness.checkout) == harness.revision
    assert harness.baseline() == before
    assert harness.state()["ce_revision"] == harness.revision


# --------------------------------------------------------------------------
# doctor: state revision, skill coverage, missing fragments
# --------------------------------------------------------------------------


def test_doctor_detects_a_state_revision_that_differs_from_the_manifest(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    state = harness.state()
    state["ce_revision"] = "b" * 40
    harness.state_path.write_text(json.dumps(state, indent=2) + "\n")

    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )

    assert "state-revision" in failures(findings)


@pytest.mark.parametrize("target", ["claude", "vibe"])
def test_doctor_detects_a_missing_managed_ce_skill_in_each_harness(harness, target):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    (harness.dest(target) / "ce-plan").unlink()

    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )

    missing = [
        f for f in findings if f.check == "skill-coverage" and f.level == "error"
    ]
    assert len(missing) == 1
    assert str(harness.dest(target)) in missing[0].message
    assert "ce-plan" in missing[0].message


def test_doctor_reports_a_missing_instruction_fragment_as_a_finding(harness):
    harness.activate_ce()
    harness.write_instructions("compound-engineering")
    (harness.stack / "agents.md.d" / "10-compound-engineering.md").unlink()

    findings = harness.controller.doctor(
        "compound-engineering", cwd=harness.tmp_path
    )

    instructions = [f for f in findings if f.check == "instructions"]
    assert instructions
    assert all(f.level == "error" for f in instructions)
    assert "10-compound-engineering.md" in instructions[0].message


# --------------------------------------------------------------------------
# installer orchestration
# --------------------------------------------------------------------------


def test_installer_runs_the_methodology_lifecycle_without_linking_skills(tmp_path):
    home = tmp_path / "home"
    stack = home / ".config/agent-stack"
    stack.mkdir(parents=True)
    install = stack / "install.sh"
    shutil.copy2(STACK_SOURCE / "install.sh", install)
    (stack / "profile.yaml").write_text("methodology: superpowers\n")
    write_skill(stack / "skills", "example")

    subprocess.run(
        ["git", "init", "--bare", "-q", str(home / ".cfg")],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (home / ".cfg/info/exclude").write_text("*\n")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls"
    pi_log = tmp_path / "pi-calls"
    python = fake_bin / "python3"
    python.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = -c ]; then exit 0; fi\n"
        "printf '%s' \"$(basename \"$1\")\" >>\"$AGENT_STACK_CALL_LOG\"\n"
        "shift\n"
        "for arg in \"$@\"; do printf ' %s' \"$arg\" >>\"$AGENT_STACK_CALL_LOG\"; done\n"
        "printf '\\n' >>\"$AGENT_STACK_CALL_LOG\"\n"
    )
    python.chmod(0o755)
    pi = fake_bin / "pi"
    pi.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >>\"$AGENT_STACK_PI_LOG\"\n")
    pi.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "AGENT_STACK_CALL_LOG": str(call_log),
            "AGENT_STACK_PI_LOG": str(pi_log),
        }
    )
    subprocess.run(
        ["bash", str(install)],
        check=True,
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    profile = stack / "profile.yaml"
    assert call_log.read_text().splitlines() == [
        f"methodology.py prepare --profile {profile}",
        f"render.py validate --profile {profile}",
        f"methodology.py activate --profile {profile}",
        "render.py",
        f"methodology.py doctor --profile {profile}",
    ]
    assert not pi_log.exists()
    for destination in (
        home / ".pi/agent/skills",
        home / ".claude/skills",
        home / ".vibe/skills",
    ):
        assert not os.path.lexists(destination)
