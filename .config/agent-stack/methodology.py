#!/usr/bin/env python3
"""Reversible global methodology controller for the agent stack.

Owns everything that switching between Superpowers and Compound Engineering
touches: manifest validation, the pinned CE checkout, pre-transition snapshots,
Pi package registration, and managed skill links in Pi, Claude, and Vibe.

Two safety rules drive the design:

* Only entries this stack owns may be removed. A managed entry is a symlink
  resolving beneath the stack Superpowers source or the managed CE checkout.
  Real files, real directories, and unrelated symlinks are preserved, and a name
  collision stops the transition before anything is replaced.
* Nothing is mutated until the whole transition has been planned and validated,
  so a rejected activation leaves links, packages, and state untouched.

Home, stack, and the external command runner are injected, so tests never read
or write a live harness directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

import yaml

STACK = Path(__file__).resolve().parent
STATE_VERSION = 1
SUPERPOWERS = "superpowers"
COMPOUND_ENGINEERING = "compound-engineering"
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
# Source prefixes pi treats as remote; everything else is a local path
# (pi's utils/paths.js: isLocalPath).
PI_REMOTE_PREFIXES = ("npm:", "git:", "github:", "http:", "https:", "ssh:")


def _load_render():
    """Load render.py by path so the fragment map has a single definition."""
    name = "agent_stack_render"
    if name in sys.modules:
        return sys.modules[name]
    loader = SourceFileLoader(name, str(STACK / "render.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules during class
    # creation, so the module has to be registered before it is executed.
    sys.modules[name] = module
    try:
        loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


_render = _load_render()
ConfigError = _render.ConfigError
METHODOLOGY_FRAGMENTS = _render.METHODOLOGY_FRAGMENTS


class MethodologyError(RuntimeError):
    """Raised when a transition cannot be performed safely."""


def run_command(args, *, cwd=None, check=True, env=None):
    return subprocess.run(
        [str(a) for a in args],
        cwd=None if cwd is None else str(cwd),
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompoundEngineeringSpec:
    repository: str
    revision: str
    checkout: Path
    expected_skill_count: int
    pi_companions: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    path: Path
    version: int
    superpowers_skills_path: str
    compound_engineering: CompoundEngineeringSpec | None

    @property
    def names(self) -> tuple[str, ...]:
        if self.compound_engineering is None:
            return (SUPERPOWERS,)
        return (SUPERPOWERS, COMPOUND_ENGINEERING)

    @property
    def ce(self) -> CompoundEngineeringSpec:
        if self.compound_engineering is None:
            raise ConfigError(
                f"{self.path}: methodologies.{COMPOUND_ENGINEERING} is missing."
            )
        return self.compound_engineering

    def to_json(self) -> dict:
        methodologies: dict = {
            SUPERPOWERS: {"skills_path": self.superpowers_skills_path}
        }
        if self.compound_engineering is not None:
            spec = self.compound_engineering
            methodologies[COMPOUND_ENGINEERING] = {
                "repository": spec.repository,
                "revision": spec.revision,
                "checkout": str(spec.checkout),
                "expected_skill_count": spec.expected_skill_count,
                "pi_companions": list(spec.pi_companions),
            }
        return {"version": self.version, "methodologies": methodologies}


def _field(mapping: dict, key: str, kind, source: Path, prefix: str = ""):
    path = f"{prefix}.{key}" if prefix else key
    if key not in mapping:
        raise ConfigError(f"{source}: {path} is missing.")
    value = mapping[key]
    if kind is int and isinstance(value, bool):
        raise ConfigError(f"{source}: {path} must be an integer; got {value!r}.")
    if not isinstance(value, kind):
        raise ConfigError(
            f"{source}: {path} must be {kind.__name__}; got {value!r}."
        )
    return value


def _expand_home(value: str, home: Path) -> Path:
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    return Path(value)


def load_manifest(path: Path, *, home: Path) -> Manifest:
    """Load methodologies.yaml strictly, naming the field path on any error."""
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError as error:
        raise ConfigError(f"{path}: methodology manifest is missing.") from error
    return parse_manifest(text, path=path, home=home)


def parse_manifest(text: str, *, path: Path, home: Path) -> Manifest:
    """Parse manifest text strictly; `path` only names the source in errors.

    Keeping parsing separate from reading lets a transaction validate a
    candidate manifest before it replaces anything on disk.
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: manifest is not valid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: manifest must be a mapping.")

    version = _field(raw, "version", int, path)
    methodologies = _field(raw, "methodologies", dict, path)
    superpowers = _field(methodologies, SUPERPOWERS, dict, path, "methodologies")
    skills_path = _field(
        superpowers, "skills_path", str, path, f"methodologies.{SUPERPOWERS}"
    )
    unknown = sorted(set(methodologies) - set(METHODOLOGY_FRAGMENTS))
    if unknown:
        raise ConfigError(
            f"{path}: methodologies.{unknown[0]} has no instruction fragment; "
            f"known methodologies are {', '.join(sorted(METHODOLOGY_FRAGMENTS))}."
        )
    if COMPOUND_ENGINEERING not in methodologies:
        return Manifest(
            path=path,
            version=version,
            superpowers_skills_path=skills_path,
            compound_engineering=None,
        )

    prefix = f"methodologies.{COMPOUND_ENGINEERING}"
    ce = _field(methodologies, COMPOUND_ENGINEERING, dict, path, "methodologies")
    revision = _field(ce, "revision", str, path, prefix)
    if not REVISION_PATTERN.fullmatch(revision):
        raise ConfigError(
            f"{path}: {prefix}.revision must be a full 40-character commit sha; "
            f"got {revision!r}."
        )
    companions = _field(ce, "pi_companions", list, path, prefix)
    for index, companion in enumerate(companions):
        if not isinstance(companion, str):
            raise ConfigError(
                f"{path}: {prefix}.pi_companions[{index}] must be a string; "
                f"got {companion!r}."
            )
    return Manifest(
        path=path,
        version=version,
        superpowers_skills_path=skills_path,
        compound_engineering=CompoundEngineeringSpec(
            repository=_field(ce, "repository", str, path, prefix),
            revision=revision,
            checkout=_expand_home(_field(ce, "checkout", str, path, prefix), home),
            expected_skill_count=_field(
                ce, "expected_skill_count", int, path, prefix
            ),
            pi_companions=tuple(companions),
        ),
    )


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------


@dataclass
class MethodologyState:
    version: int = STATE_VERSION
    active: str = SUPERPOWERS
    ce_revision: str | None = None
    managed_links: list[str] = field(default_factory=list)
    pi_ask_user_added: bool = False

    def to_json(self) -> dict:
        return {
            "version": self.version,
            "active": self.active,
            "ce_revision": self.ce_revision,
            "managed_links": list(self.managed_links),
            "pi_ask_user_added": self.pi_ask_user_added,
        }


def load_state(path: Path) -> MethodologyState:
    path = Path(path)
    if not path.exists():
        return MethodologyState()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: state file is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: state file must be a JSON object.")
    version = _field(raw, "version", int, path)
    if version != STATE_VERSION:
        raise ConfigError(
            f"{path}: version {version} is not supported by this controller "
            f"(expected {STATE_VERSION})."
        )
    active = _field(raw, "active", str, path)
    if active not in METHODOLOGY_FRAGMENTS:
        raise ConfigError(
            f"{path}: active must be one of "
            f"{', '.join(sorted(METHODOLOGY_FRAGMENTS))}; got {active!r}."
        )
    links = _field(raw, "managed_links", list, path)
    for index, link in enumerate(links):
        if not isinstance(link, str):
            raise ConfigError(
                f"{path}: managed_links[{index}] must be a string; got {link!r}."
            )
    if "ce_revision" not in raw:
        raise ConfigError(f"{path}: ce_revision is missing.")
    revision = raw["ce_revision"]
    if active == SUPERPOWERS:
        if revision is not None:
            raise ConfigError(
                f"{path}: ce_revision must be null while {SUPERPOWERS} is "
                f"active; got {revision!r}."
            )
    elif not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision):
        raise ConfigError(
            f"{path}: ce_revision must be a full 40-character commit sha while "
            f"{active} is active; got {revision!r}."
        )
    return MethodologyState(
        version=version,
        active=active,
        ce_revision=revision,
        managed_links=list(links),
        pi_ask_user_added=_field(raw, "pi_ask_user_added", bool, path),
    )


def _write_atomically(path: Path, content: str) -> bool:
    """Write `content` to `path`; return False when the bytes already match.

    Skipping an identical write is what keeps a repeated activation free of any
    state churn, including the file's mtime.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return False
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    temporary.write_text(content)
    os.replace(temporary, path)
    return True


def save_state(path: Path, state: MethodologyState) -> bool:
    return _write_atomically(path, json.dumps(state.to_json(), indent=2) + "\n")


# ---------------------------------------------------------------------------
# link planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    level: str
    check: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.check}: {self.message}"


@dataclass
class LinkJournal:
    """What an applied link plan changed, so a failure can undo it exactly."""

    removed: list[tuple[Path, str]] = field(default_factory=list)
    created: list[Path] = field(default_factory=list)
    created_dirs: list[Path] = field(default_factory=list)


@dataclass
class LinkPlan:
    creates: list[tuple[Path, Path]] = field(default_factory=list)
    removals: list[Path] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.creates and not self.removals


def _link_target(link: Path) -> Path:
    target = Path(os.readlink(link))
    if not target.is_absolute():
        target = link.parent / target
    return Path(os.path.normpath(target))


def _is_beneath(path: Path, root: Path) -> bool:
    resolved = Path(os.path.realpath(path))
    base = Path(os.path.realpath(root))
    return resolved == base or base in resolved.parents


def _skill_entries(directory: Path) -> dict[str, Path]:
    """Direct `*/SKILL.md` skill directories, keyed by name."""
    if not directory.is_dir():
        return {}
    return {
        entry.name: entry
        for entry in sorted(directory.iterdir())
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    }


# ---------------------------------------------------------------------------
# controller
# ---------------------------------------------------------------------------


class Controller:
    def __init__(
        self,
        *,
        home: Path,
        stack: Path | None = None,
        profile: Path | None = None,
        manifest: Manifest | None = None,
        runner=run_command,
        clock=None,
    ):
        self.home = Path(home)
        self.stack = Path(stack) if stack is not None else STACK
        self.profile_path = (
            Path(profile) if profile is not None else self.stack / "profile.yaml"
        )
        self.runner = runner
        self._clock = clock or datetime.now
        self.manifest = manifest or load_manifest(
            self.stack / "methodologies.yaml", home=self.home
        )

    # -- paths -------------------------------------------------------------

    @property
    def state_dir(self) -> Path:
        return self.home / ".local/state/agent-stack"

    @property
    def state_path(self) -> Path:
        return self.state_dir / "methodology.json"

    @property
    def migrations_dir(self) -> Path:
        return self.state_dir / "migrations"

    @property
    def pi_settings_path(self) -> Path:
        return self.home / ".pi/agent/settings.json"

    @property
    def superpowers_skills(self) -> Path:
        return self.stack / self.manifest.superpowers_skills_path

    @property
    def ce_checkout(self) -> Path:
        return self.manifest.ce.checkout

    @property
    def ce_skills(self) -> Path:
        return self.ce_checkout / "skills"

    @property
    def skill_destinations(self) -> dict[str, Path]:
        return {
            "pi": self.home / ".pi/agent/skills",
            "claude": self.home / ".claude/skills",
            "vibe": self.home / ".vibe/skills",
        }

    @property
    def instruction_targets(self) -> list[Path]:
        return [
            self.home / ".pi/agent/AGENTS.md",
            self.home / ".vibe/AGENTS.md",
            self.home / ".config/opencode/AGENTS.md",
            self.home / ".claude/CLAUDE.md",
        ]

    @property
    def artifact_resolver(self) -> Path:
        return self.stack / "bin/ce-artifact-root"

    # -- profile -----------------------------------------------------------

    def selected_methodology(self, profile_path: Path | None = None) -> str:
        path = Path(profile_path) if profile_path is not None else self.profile_path
        try:
            raw = yaml.safe_load(path.read_text())
        except FileNotFoundError as error:
            raise ConfigError(f"{path}: profile is missing.") from error
        except yaml.YAMLError as error:
            raise ConfigError(f"{path}: profile is not valid YAML: {error}") from error
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: profile must be a mapping.")
        name = raw.get("methodology", SUPERPOWERS)
        if not isinstance(name, str) or name not in self.manifest.names:
            raise ConfigError(
                f"{path}: methodology {name!r} is not defined in "
                f"{self.manifest.path}; known methodologies are "
                f"{', '.join(self.manifest.names)}."
            )
        return name

    # -- git helpers -------------------------------------------------------

    def _git(self, *args: str, cwd: Path | None = None, check: bool = True):
        try:
            return self.runner(["git", *args], cwd=cwd, check=check)
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            raise MethodologyError(
                f"git {' '.join(args)} failed"
                + (f" in {cwd}" if cwd else "")
                + (f": {detail}" if detail else "")
            ) from error

    def _head_revision(self, checkout: Path) -> str | None:
        if not (checkout / ".git").exists():
            return None
        result = self._git("rev-parse", "HEAD", cwd=checkout, check=False)
        if result.returncode != 0:
            return None
        return (result.stdout or "").strip()

    def _has_commit(self, checkout: Path, revision: str) -> bool:
        result = self._git(
            "cat-file", "-e", f"{revision}^{{commit}}", cwd=checkout, check=False
        )
        return result.returncode == 0

    # -- prepare -----------------------------------------------------------

    def prepare(self, name: str, *, revision: str | None = None) -> list[str]:
        if name == SUPERPOWERS:
            if revision is not None:
                raise ConfigError(f"{SUPERPOWERS} does not take a revision.")
            return self._prepare_superpowers()
        if name == COMPOUND_ENGINEERING:
            messages, retired = self._prepare_compound_engineering(revision)
            self._discard(retired)
            return messages
        raise ConfigError(f"unknown methodology {name!r}.")

    @staticmethod
    def _require_full_revision(revision, label: str) -> str:
        """Reject anything but a full 40-character sha before any mutation.

        An abbreviated sha checks out fine but cannot be written back to the
        manifest, which validates full shas, so it must fail up front.
        """
        text = revision.strip() if isinstance(revision, str) else revision
        if not isinstance(text, str) or not REVISION_PATTERN.fullmatch(text):
            raise ConfigError(
                f"{label} must be a full 40-character commit sha; got "
                f"{revision!r}."
            )
        return text

    @staticmethod
    def _discard(path: Path | None) -> None:
        if path is not None and path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _prepare_superpowers(self) -> list[str]:
        source = self.superpowers_skills
        if not source.is_dir():
            raise MethodologyError(f"superpowers source {source} is missing.")
        incomplete = [
            entry.name
            for entry in sorted(source.iterdir())
            if entry.is_dir() and not (entry / "SKILL.md").is_file()
        ]
        if incomplete:
            raise MethodologyError(
                f"{source}: skill directories without SKILL.md: "
                f"{', '.join(incomplete)}"
            )
        return [f"superpowers source ok: {len(_skill_entries(source))} skills"]

    def _prepare_compound_engineering(
        self, revision: str | None, *, retain_previous: bool = False
    ) -> tuple[list[str], Path | None]:
        """Install the pinned checkout; return messages and the retired copy.

        With `retain_previous`, the replaced checkout is kept aside so a caller
        can restore it byte-identically; the caller then owns discarding it.
        """
        spec = self.manifest.ce
        wanted = (
            spec.revision
            if revision is None
            else self._require_full_revision(revision, "revision")
        )
        checkout = spec.checkout
        if self._head_revision(checkout) == wanted and not self._validate_checkout(
            checkout, spec.expected_skill_count
        ):
            return [f"compound-engineering checkout already at {wanted}"], None

        checkout.parent.mkdir(parents=True, exist_ok=True)
        candidate = self._temporary_sibling(checkout, "tmp")
        try:
            origin = (
                str(checkout) if (checkout / ".git").exists() else spec.repository
            )
            self._git("clone", "--quiet", origin, str(candidate))
            self._git(
                "remote", "set-url", "origin", spec.repository, cwd=candidate
            )
            if not self._has_commit(candidate, wanted):
                self._git("fetch", "--quiet", "origin", wanted, cwd=candidate)
            self._git("checkout", "--quiet", "--detach", wanted, cwd=candidate)
            problems = self._validate_checkout(candidate, spec.expected_skill_count)
            if problems:
                raise MethodologyError(
                    "\n".join(
                        [f"candidate checkout {wanted} is invalid:", *problems]
                    )
                )
            retired = self._install_checkout(
                candidate, checkout, retain_previous=retain_previous
            )
        finally:
            if candidate.exists():
                shutil.rmtree(candidate, ignore_errors=True)
        return [f"compound-engineering checkout installed at {wanted}"], retired

    def _validate_checkout(self, root: Path, expected_skill_count: int) -> list[str]:
        problems: list[str] = []
        package = root / "package.json"
        if not package.is_file():
            problems.append(f"{package} is missing")
        else:
            try:
                json.loads(package.read_text())
            except json.JSONDecodeError as error:
                problems.append(f"{package} is not valid JSON: {error}")
        extension = root / ".pi/extensions/compound-engineering.ts"
        if not extension.is_file():
            problems.append(f"{extension} is missing")
        found = len(_skill_entries(root / "skills"))
        if found != expected_skill_count:
            problems.append(
                f"{root}/skills holds {found} direct skills with SKILL.md; "
                f"the manifest expects {expected_skill_count}"
            )
        return problems

    def _temporary_sibling(self, target: Path, tag: str) -> Path:
        return target.parent / (
            f".{target.name}.{tag}-{os.getpid()}-{secrets.token_hex(4)}"
        )

    def _install_checkout(
        self, candidate: Path, target: Path, *, retain_previous: bool = False
    ) -> Path | None:
        retired = None
        if target.exists() or target.is_symlink():
            retired = self._temporary_sibling(target, "previous")
            os.rename(target, retired)
        try:
            os.rename(candidate, target)
        except OSError:
            if retired is not None:
                os.rename(retired, target)
            raise
        if retired is not None and not retain_previous:
            shutil.rmtree(retired, ignore_errors=True)
            return None
        return retired

    def _restore_checkout(self, retired: Path | None) -> None:
        """Put a retired checkout back, byte-identically, after a failure."""
        if retired is None or not retired.exists():
            return
        target = self.ce_checkout
        replaced = None
        if target.exists() or target.is_symlink():
            replaced = self._temporary_sibling(target, "rollback")
            os.rename(target, replaced)
        os.rename(retired, target)
        self._discard(replaced)

    # -- update ------------------------------------------------------------

    def update(self, revision: str) -> list[str]:
        """Move the pin to `revision` as one transaction.

        Everything that can be checked without mutating anything is checked
        first: the sha shape, the manifest rewrite, and a strict parse of the
        candidate manifest. Only then is the checkout replaced and the manifest
        written, and any failure afterwards restores both byte-identically.
        """
        revision = self._require_full_revision(revision, "--revision")
        path = self.manifest.path
        previous = self.manifest.ce.revision
        original = path.read_text()
        candidate_text = self._candidate_manifest_text(original, previous, revision)
        candidate = parse_manifest(candidate_text, path=path, home=self.home)
        if candidate.ce.revision != revision:
            raise MethodologyError(
                f"{path}: the candidate manifest pins "
                f"{candidate.ce.revision}, not {revision}."
            )
        messages = [
            f"current pinned revision: {previous}",
            f"candidate revision:      {revision}",
        ]

        retired = None
        try:
            prepared, retired = self._prepare_compound_engineering(
                revision, retain_previous=True
            )
            _write_atomically(path, candidate_text)
            self.manifest = load_manifest(path, home=self.home)
        except BaseException:
            self._restore_manifest(path, original)
            self._restore_checkout(retired)
            raise
        finally:
            self._discard(retired)
        messages += prepared
        messages.append(f"manifest revision updated: {previous} -> {revision}")
        return messages

    def _candidate_manifest_text(
        self, text: str, previous: str, revision: str
    ) -> str:
        path = self.manifest.path
        if previous == revision:
            return text
        occurrences = text.count(previous)
        if occurrences != 1:
            raise MethodologyError(
                f"{path}: expected exactly one occurrence of {previous}; "
                f"found {occurrences}. Update the manifest by hand."
            )
        return text.replace(previous, revision, 1)

    def _restore_manifest(self, path: Path, original: str) -> None:
        try:
            if path.read_text() == original:
                return
        except OSError:
            pass
        _write_atomically(path, original)

    # -- snapshots ---------------------------------------------------------

    def snapshot(self, from_name: str, to_name: str) -> Path:
        stamp = self._clock().strftime("%Y%m%d%H%M%S")
        base = self.migrations_dir / f"{stamp}-{from_name}-to-{to_name}"
        directory = base
        suffix = 1
        while directory.exists():
            suffix += 1
            directory = base.parent / f"{base.name}-{suffix}"
        (directory / "instructions").mkdir(parents=True)

        (directory / "manifest.json").write_text(
            json.dumps(self.manifest.to_json(), indent=2) + "\n"
        )
        if self.profile_path.is_file():
            shutil.copy2(self.profile_path, directory / "profile.yaml")
        if self.pi_settings_path.is_file():
            shutil.copy2(self.pi_settings_path, directory / "pi-settings.json")
        for target in self.instruction_targets:
            if target.is_file():
                shutil.copy2(
                    target, directory / "instructions" / self._flat_name(target)
                )
        (directory / "skill-links.json").write_text(
            json.dumps(self.link_inventory(), indent=2) + "\n"
        )
        return directory

    def _flat_name(self, path: Path) -> str:
        try:
            relative = path.relative_to(self.home)
        except ValueError:
            relative = Path(*path.parts[1:]) if path.is_absolute() else path
        return str(relative).replace("/", "__")

    def link_inventory(self) -> dict[str, dict[str, dict]]:
        inventory: dict[str, dict[str, dict]] = {}
        for destination in self.skill_destinations.values():
            entries: dict[str, dict] = {}
            if destination.is_dir() and not destination.is_symlink():
                for entry in sorted(destination.iterdir()):
                    if entry.is_symlink():
                        entries[entry.name] = {
                            "type": "symlink",
                            "target": str(_link_target(entry)),
                        }
                    else:
                        entries[entry.name] = {
                            "type": "directory" if entry.is_dir() else "file",
                            "target": None,
                        }
            inventory[str(destination)] = entries
        return inventory

    # -- managed links -----------------------------------------------------

    def _managed_roots(self) -> tuple[Path, ...]:
        if self.manifest.compound_engineering is None:
            return (self.superpowers_skills,)
        return (self.superpowers_skills, self.ce_checkout)

    def _is_managed(self, link: Path) -> bool:
        target = _link_target(link)
        return any(_is_beneath(target, root) for root in self._managed_roots())

    def _desired_links(self, name: str) -> dict[str, dict[str, Path]]:
        """Skill links each destination must hold for `name`.

        Pi receives CE through its local package registration, so CE mode plans
        no Pi skill links at all.
        """
        if name == SUPERPOWERS:
            skills = _skill_entries(self.superpowers_skills)
            return {harness: dict(skills) for harness in self.skill_destinations}
        skills = _skill_entries(self.ce_skills)
        return {
            "pi": {},
            "claude": dict(skills),
            "vibe": dict(skills),
        }

    def _preflight_destinations(self) -> None:
        """Reject every unsafe skill-destination topology before planning.

        Each destination must be a real directory (or absent) inside the
        expected home: a regular file, a symlinked destination, or a symlinked
        ancestor escaping home would make link creation land somewhere this
        controller does not own. All destinations are checked before any of
        them is planned, so no partial work can precede a rejection.
        """
        home = Path(os.path.realpath(self.home))
        for destination in self.skill_destinations.values():
            try:
                relative = destination.relative_to(self.home)
            except ValueError as error:
                raise MethodologyError(
                    f"{destination} is not inside {self.home}."
                ) from error
            current = self.home
            for part in relative.parts:
                current = current / part
                if not current.is_symlink():
                    continue
                resolved = Path(os.path.realpath(current))
                if resolved != home and home not in resolved.parents:
                    raise MethodologyError(
                        f"{current} is a symlink to {resolved}, outside the "
                        f"expected home {self.home}; replace it with a real "
                        "directory before switching methodology."
                    )
            if destination.is_symlink():
                raise MethodologyError(
                    f"{destination} is a symlink to {_link_target(destination)}; "
                    "replace it with a real directory before switching methodology."
                )
            if destination.exists() and not destination.is_dir():
                raise MethodologyError(
                    f"{destination} exists but is not a directory; "
                    "move it aside before switching methodology."
                )

    def _plan_links(self, name: str) -> LinkPlan:
        plan = LinkPlan()
        self._preflight_destinations()
        desired_by_harness = self._desired_links(name)
        for harness, destination in self.skill_destinations.items():
            desired = desired_by_harness[harness]
            existing = (
                {entry.name: entry for entry in sorted(destination.iterdir())}
                if destination.is_dir()
                else {}
            )
            for skill, source in desired.items():
                link = destination / skill
                current = existing.get(skill)
                if current is None:
                    plan.creates.append((link, source))
                elif not current.is_symlink():
                    raise MethodologyError(
                        f"{link} already exists and is not a link this stack owns; "
                        "move it aside before switching methodology."
                    )
                elif _link_target(current) == source:
                    pass
                elif self._is_managed(current):
                    plan.removals.append(link)
                    plan.creates.append((link, source))
                else:
                    raise MethodologyError(
                        f"{link} points at {_link_target(current)}, which this "
                        "stack does not manage; move it aside before switching "
                        "methodology."
                    )
                plan.links.append(str(link))
            for skill, entry in existing.items():
                if skill in desired:
                    continue
                if entry.is_symlink() and self._is_managed(entry):
                    plan.removals.append(entry)
        plan.links.sort()
        return plan

    def _apply_links(self, plan: LinkPlan, journal: LinkJournal) -> None:
        """Apply the plan, recording in `journal` enough to undo it exactly.

        The journal is filled as the work happens, so a partially applied plan
        is still fully reversible by the caller.
        """
        for link in plan.removals:
            journal.removed.append((link, os.readlink(link)))
            link.unlink()
        for link, source in plan.creates:
            parent = link.parent
            if not parent.exists():
                missing = [parent]
                while not missing[-1].parent.exists():
                    missing.append(missing[-1].parent)
                parent.mkdir(parents=True)
                journal.created_dirs.extend(reversed(missing))
            link.symlink_to(source)
            journal.created.append(link)

    def _undo_links(self, journal: LinkJournal) -> list[str]:
        failures: list[str] = []
        for link in reversed(journal.created):
            try:
                if link.is_symlink():
                    link.unlink()
            except OSError as error:  # pragma: no cover - defensive
                failures.append(f"could not remove {link}: {error}")
        for directory in reversed(journal.created_dirs):
            try:
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
            except OSError as error:  # pragma: no cover - defensive
                failures.append(f"could not remove {directory}: {error}")
        for link, target in reversed(journal.removed):
            try:
                if not link.is_symlink() and not link.exists():
                    os.symlink(target, link)
            except OSError as error:  # pragma: no cover - defensive
                failures.append(f"could not restore {link} -> {target}: {error}")
        journal.created.clear()
        journal.created_dirs.clear()
        journal.removed.clear()
        return failures

    # -- pi packages -------------------------------------------------------

    def _pi_settings(self) -> dict:
        if not self.pi_settings_path.is_file():
            return {}
        try:
            settings = json.loads(self.pi_settings_path.read_text())
        except json.JSONDecodeError as error:
            raise MethodologyError(
                f"{self.pi_settings_path}: settings are not valid JSON: {error}"
            ) from error
        if not isinstance(settings, dict):
            raise MethodologyError(
                f"{self.pi_settings_path}: settings must be a JSON object."
            )
        return settings

    def _pi_packages(self) -> list[str]:
        """The configured package sources, string and object entries alike.

        pi accepts both ``"npm:foo"`` and ``{"source": "npm:foo", ...}`` in
        ``settings.packages`` (``getPackageSourceString``), so both forms are
        read here; only their source strings matter to this controller.
        """
        packages = self._pi_settings().get("packages", [])
        if not isinstance(packages, list):
            raise MethodologyError(
                f"{self.pi_settings_path}: packages must be a list."
            )
        sources: list[str] = []
        for entry in packages:
            if isinstance(entry, str):
                sources.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("source"), str):
                sources.append(entry["source"])
        return sources

    def _package_source_path(self, entry: str) -> Path | None:
        """Resolve a local package source exactly the way pi resolves it.

        pi treats every source that is not ``npm:``/``git:``/``github:``/
        ``http(s):``/``ssh:`` as a local path, expands a leading ``~``, and
        resolves a relative path against the agent directory for user scope
        (``resolvePathFromBase(path, agentDir)``). Resolution is lexical: pi
        never calls realpath, so neither does this.
        """
        text = entry.strip()
        if not text or text.startswith(PI_REMOTE_PREFIXES):
            return None
        expanded = _expand_home(text, self.home)
        if not expanded.is_absolute():
            expanded = self.pi_settings_path.parent / expanded
        return Path(os.path.normpath(expanded))

    def _ce_package_entry(self, packages: list[str]) -> str | None:
        """The pi packages entry registering the managed CE checkout, if any.

        The match is exact: an entry naming a descendant of the checkout is a
        different package and must never be treated as ours, or removing CE
        would remove somebody else's registration.
        """
        checkout = Path(os.path.normpath(self.ce_checkout))
        for entry in packages:
            if self._package_source_path(entry) == checkout:
                return entry
        return None

    def _plan_packages(
        self, name: str, state: MethodologyState
    ) -> tuple[list[tuple[str, str]], bool]:
        packages = self._pi_packages()
        registered = self._ce_package_entry(packages)
        operations: list[tuple[str, str]] = []
        ask_user_added = state.pi_ask_user_added
        if name == COMPOUND_ENGINEERING:
            if "npm:pi-subagents" not in packages:
                raise MethodologyError(
                    "pi package npm:pi-subagents is not installed; install it "
                    "before activating compound-engineering."
                )
            if registered is None:
                operations.append(("install", str(self.ce_checkout)))
            if "npm:pi-ask-user" not in packages:
                operations.append(("install", "npm:pi-ask-user"))
                ask_user_added = True
        else:
            if registered is not None:
                # pi resolves a remove argument against the process cwd, so
                # the absolute checkout path is the only representation that
                # reliably matches the recorded (agent-dir relative) entry.
                operations.append(("remove", str(self.ce_checkout)))
            if ask_user_added and "npm:pi-ask-user" in packages:
                operations.append(("remove", "npm:pi-ask-user"))
            ask_user_added = False
        return operations, ask_user_added

    def _apply_packages(
        self, operations: list[tuple[str, str]], applied: list[tuple[str, str]]
    ) -> None:
        for operation, source in operations:
            try:
                self.runner(["pi", operation, source])
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or error.stdout or "").strip()
                raise MethodologyError(
                    f"pi {operation} {source} failed"
                    + (f": {detail}" if detail else "")
                ) from error
            applied.append((operation, source))

    def _undo_packages(self, applied: list[tuple[str, str]]) -> list[str]:
        inverse = {"install": "remove", "remove": "install"}
        failures: list[str] = []
        for operation, source in reversed(applied):
            try:
                self.runner(["pi", inverse[operation], source])
            except Exception as error:  # pragma: no cover - defensive
                failures.append(f"pi {inverse[operation]} {source} failed: {error}")
        return failures

    # -- activation --------------------------------------------------------

    def activate(self, name: str) -> list[str]:
        if name not in self.manifest.names:
            raise ConfigError(
                f"unknown methodology {name!r}; known methodologies are "
                f"{', '.join(self.manifest.names)}."
            )
        state = load_state(self.state_path)
        if name == COMPOUND_ENGINEERING:
            problems = self._validate_checkout(
                self.ce_checkout, self.manifest.ce.expected_skill_count
            )
            if problems:
                raise MethodologyError(
                    "\n".join(
                        [
                            "the compound-engineering checkout is not ready; "
                            "run `methodology.py prepare` first:",
                            *problems,
                        ]
                    )
                )
            self._require_pinned_checkout()
        else:
            self._prepare_superpowers()

        plan = self._plan_links(name)
        operations, ask_user_added = self._plan_packages(name, state)
        desired = MethodologyState(
            version=STATE_VERSION,
            active=name,
            ce_revision=(
                self._head_revision(self.ce_checkout)
                if name == COMPOUND_ENGINEERING
                else None
            ),
            managed_links=plan.links,
            pi_ask_user_added=ask_user_added,
        )
        if plan.empty and not operations and desired == state:
            return [f"{name} already active; no changes"]

        snapshot = self.snapshot(state.active, name)
        messages = [f"snapshot: {snapshot}"]
        journal = LinkJournal()
        applied: list[tuple[str, str]] = []
        try:
            self._apply_links(plan, journal)
            self._apply_packages(operations, applied)
            save_state(self.state_path, desired)
        except BaseException as error:
            failures = self._undo_packages(applied)
            failures += self._undo_links(journal)
            self._discard_snapshot(snapshot)
            if failures:
                raise MethodologyError(
                    "\n".join([f"{error}", "rollback was incomplete:", *failures])
                ) from error
            raise
        messages.append(
            f"activated {name}: {len(plan.creates)} link(s) created, "
            f"{len(plan.removals)} managed link(s) removed, "
            f"{len(operations)} pi package change(s)"
        )
        return messages

    def _require_pinned_checkout(self) -> None:
        """Fail before any mutation unless the checkout is exactly the pin.

        Activation links every harness at this checkout, so its content has to
        be the reviewed revision: a drifted HEAD or an edited tracked file
        would publish something nobody reviewed.
        """
        spec = self.manifest.ce
        head = self._head_revision(spec.checkout)
        if head is None:
            raise MethodologyError(
                f"{spec.checkout} is not a git checkout; run "
                "`methodology.py prepare` first."
            )
        if head != spec.revision:
            raise MethodologyError(
                f"{spec.checkout} is at {head}; the manifest pins "
                f"{spec.revision}. Run `methodology.py prepare` first."
            )
        status = self._git(
            "status",
            "--porcelain",
            "--untracked-files=no",
            cwd=spec.checkout,
            check=False,
        )
        if status.returncode != 0:
            raise MethodologyError(
                f"git status failed in {spec.checkout}: "
                f"{(status.stderr or '').strip()}"
            )
        dirty = (status.stdout or "").strip()
        if dirty:
            raise MethodologyError(
                f"{spec.checkout} has uncommitted changes to tracked files, so "
                f"it no longer matches the pinned revision {spec.revision}:\n"
                f"{dirty}"
            )

    def _discard_snapshot(self, snapshot: Path) -> None:
        """Drop a snapshot taken for an activation that was rolled back."""
        if snapshot.is_dir() and not snapshot.is_symlink():
            shutil.rmtree(snapshot, ignore_errors=True)

    # -- doctor ------------------------------------------------------------

    def doctor(self, name: str, *, cwd: Path) -> list[Finding]:
        findings: list[Finding] = []
        findings += self._check_instructions(name)
        if name == COMPOUND_ENGINEERING:
            findings += self._check_checkout()
            findings += self._check_pi_packages()
        findings += self._check_managed_links(name)
        findings += self._check_discovery(name)
        findings += self._check_artifact_root(Path(cwd))
        findings += self._check_vibe(name)
        return findings

    def _check_instructions(self, name: str) -> list[Finding]:
        fragments = self.stack / "agents.md.d"
        selected = (fragments / METHODOLOGY_FRAGMENTS[name]).read_text().strip()
        inactive = [
            (other, (fragments / filename).read_text().strip())
            for other, filename in METHODOLOGY_FRAGMENTS.items()
            if other != name
        ]
        findings: list[Finding] = []
        for target in self.instruction_targets:
            if not target.is_file():
                findings.append(
                    Finding("error", "instructions", f"{target} is missing")
                )
                continue
            content = target.read_text()
            if selected not in content:
                findings.append(
                    Finding(
                        "error",
                        "instructions",
                        f"{target} does not carry the {name} methodology fragment",
                    )
                )
            for other, text in inactive:
                if text in content:
                    findings.append(
                        Finding(
                            "error",
                            "instructions",
                            f"{target} still carries the {other} fragment",
                        )
                    )
        return findings

    def _check_checkout(self) -> list[Finding]:
        spec = self.manifest.ce
        findings: list[Finding] = []
        head = self._head_revision(spec.checkout)
        if head is None:
            return [
                Finding(
                    "error",
                    "ce-revision",
                    f"{spec.checkout} is not a git checkout",
                )
            ]
        if head != spec.revision:
            findings.append(
                Finding(
                    "error",
                    "ce-revision",
                    f"{spec.checkout} is at {head}; the manifest pins "
                    f"{spec.revision}",
                )
            )
        found = len(_skill_entries(self.ce_skills))
        if found != spec.expected_skill_count:
            findings.append(
                Finding(
                    "error",
                    "ce-skill-count",
                    f"{self.ce_skills} holds {found} skills; the manifest "
                    f"expects {spec.expected_skill_count}",
                )
            )
        return findings

    def _check_pi_packages(self) -> list[Finding]:
        spec = self.manifest.ce
        packages = self._pi_packages()
        findings = [
            Finding("error", "pi-companions", f"pi package {companion} is missing")
            for companion in spec.pi_companions
            if companion not in packages
        ]
        if self._ce_package_entry(packages) is None:
            findings.append(
                Finding(
                    "error",
                    "pi-package",
                    f"the local pi package for {spec.checkout} is not registered",
                )
            )
        return findings

    def _active_source(self, name: str) -> Path:
        return self.superpowers_skills if name == SUPERPOWERS else self.ce_skills

    def _check_managed_links(self, name: str) -> list[Finding]:
        source = self._active_source(name)
        findings: list[Finding] = []
        for recorded in load_state(self.state_path).managed_links:
            link = Path(recorded)
            if not link.is_symlink():
                findings.append(
                    Finding("error", "managed-link", f"{link} is no longer a link")
                )
            elif not link.exists():
                findings.append(
                    Finding(
                        "error",
                        "managed-link",
                        f"{link} is broken; it points at {_link_target(link)}",
                    )
                )
            elif not _is_beneath(_link_target(link), source):
                findings.append(
                    Finding(
                        "error",
                        "managed-link",
                        f"{link} points at {_link_target(link)}, outside the "
                        f"active {name} source {source}",
                    )
                )
        return findings

    def _check_discovery(self, name: str) -> list[Finding]:
        if self.manifest.compound_engineering is None:
            return []
        if name == COMPOUND_ENGINEERING:
            check, inactive_root = "superpowers-discoverable", self.superpowers_skills
        else:
            check, inactive_root = "ce-discoverable", self.ce_checkout
        inactive_names = set(_skill_entries(self._active_source(
            SUPERPOWERS if name == COMPOUND_ENGINEERING else COMPOUND_ENGINEERING
        )))
        findings: list[Finding] = []
        for destination in self.skill_destinations.values():
            if not destination.is_dir() or destination.is_symlink():
                continue
            for entry in sorted(destination.iterdir()):
                if entry.is_symlink():
                    if _is_beneath(_link_target(entry), inactive_root):
                        findings.append(
                            Finding(
                                "error",
                                check,
                                f"{entry} still resolves into the inactive "
                                f"source {inactive_root}",
                            )
                        )
                elif entry.name in inactive_names:
                    findings.append(
                        Finding(
                            "error",
                            check,
                            f"{entry} shadows an inactive-methodology skill name",
                        )
                    )
        return findings

    def _check_artifact_root(self, cwd: Path) -> list[Finding]:
        resolver = self.artifact_resolver
        if not resolver.is_file():
            return [
                Finding("warning", "artifact-root", f"{resolver} is not installed")
            ]
        environment = os.environ.copy()
        environment["HOME"] = str(self.home)
        result = self.runner(
            [str(resolver), "--cwd", str(cwd), "--no-create"],
            check=False,
            env=environment,
        )
        if result.returncode != 0:
            return [
                Finding(
                    "error",
                    "artifact-root",
                    f"{resolver} failed for {cwd}: "
                    f"{(result.stderr or '').strip()}",
                )
            ]
        root = Path((result.stdout or "").strip())
        toplevel = self._git(
            "rev-parse", "--show-toplevel", cwd=cwd, check=False
        )
        if toplevel.returncode != 0:
            return []
        repository = Path((toplevel.stdout or "").strip())
        if _is_beneath(root, repository):
            return [
                Finding(
                    "error",
                    "artifact-root",
                    f"the artifact root {root} is inside the repository "
                    f"{repository}",
                )
            ]
        return []

    def _check_vibe(self, name: str) -> list[Finding]:
        destination = self.skill_destinations["vibe"]
        expected = set(_skill_entries(self._active_source(name)))
        present = set()
        if destination.is_dir() and not destination.is_symlink():
            present = {entry.name for entry in destination.iterdir()}
        missing = sorted(expected - present)
        findings = [
            Finding(
                "error" if missing else "info",
                "vibe-discovery",
                f"{destination} is missing {len(missing)} {name} skill(s): "
                f"{', '.join(missing)}"
                if missing
                else f"{destination} exposes all {len(expected)} {name} skills",
            )
        ]
        if name == COMPOUND_ENGINEERING:
            findings.append(
                Finding(
                    "warning",
                    "vibe-native-parity",
                    "vibe is not a documented CE host: skill discovery is "
                    "checked above, native CE feature parity is unverified",
                )
            )
        else:
            findings.append(
                Finding(
                    "info",
                    "vibe-native-parity",
                    "vibe native CE feature parity is not applicable in "
                    "superpowers mode",
                )
            )
        return findings


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command", choices=("prepare", "activate", "doctor", "snapshot", "update")
    )
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--stack", type=Path, default=STACK)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--from", dest="from_name")
    parser.add_argument("--to", dest="to_name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = args.home or Path.home()
    profile = args.profile or args.stack / "profile.yaml"
    try:
        controller = Controller(home=home, stack=args.stack, profile=profile)
        if args.command == "snapshot":
            if not args.from_name or not args.to_name:
                raise ConfigError("snapshot requires --from NAME and --to NAME.")
            print(controller.snapshot(args.from_name, args.to_name))
            return 0
        if args.command == "update":
            if not args.revision:
                raise ConfigError("update requires --revision COMMIT.")
            for message in controller.update(args.revision):
                print(message)
            return 0
        name = controller.selected_methodology(profile)
        if args.command == "prepare":
            for message in controller.prepare(name):
                print(message)
            return 0
        if args.command == "activate":
            for message in controller.activate(name):
                print(message)
            return 0
        findings = controller.doctor(name, cwd=args.cwd or Path.cwd())
        for finding in findings:
            print(finding)
        failed = [f for f in findings if f.level == "error"]
        if failed:
            print(f"methodology doctor: {name} FAILED ({len(failed)} error(s))")
            return 1
        print(f"methodology doctor: {name} ok")
        return 0
    except (ConfigError, MethodologyError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    raise SystemExit(main())
