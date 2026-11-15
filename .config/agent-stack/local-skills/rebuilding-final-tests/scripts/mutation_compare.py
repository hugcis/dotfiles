#!/usr/bin/env python3
"""Compare two test suites on the same mutants of a branch's changed production lines.

    baseline --base <ref> [--paths ...] [--tests ...] --out <file>
        Mutate only the production lines the branch changed against its merge base with
        <ref> (committed, uncommitted and untracked), run the current suite against them and
        save the mutant ids, their diffs and the kill/survive result for each.

    compare --baseline <file> --out <file>
        Run the current (rebuilt) suite against exactly the saved mutant ids and report killed
        before and after, mutants each suite catches that the other misses, and survivors.

    size --base <ref> --paths <test paths> [--rev worktree|<rev>] --out <file> [--against <file>]
        Count the test definitions and lines a snapshot added or changed under the test paths since
        the merge base. With --against, exit 1 unless both are strictly below the saved count.

Exit codes: 0 ok (compare: the new suite kills at least as many), 1 compare: the new suite
kills fewer / size: not strictly smaller, 2 usage or integrity error (bad budget, failing suite,
production code changed since the baseline, timeout), 3 mutation check unavailable or partial
(no engine for some changed code file, no mutants on the changed lines, mutmut cannot run).

Only `killed`, `timeout` and `segfault` count as killed. `survived`, `no tests` and `suspicious`
count as not killed on both sides.

Python goes through mutmut (pinned to MUTMUT_VERSION). Rust and JS/TS have engine hooks
that report "unavailable" until implemented. This orchestrator only needs the standard
library; mutmut runs in the repo's environment through --runner.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MUTMUT_VERSION = "3.8.1"
DEFAULT_SEED = 1729
KILLED_STATUSES = {"killed", "timeout", "segfault"}
PER_MUTANT_OVERHEAD_S = 0.3
SETUP_SHARE_OF_BUDGET = 0.3
MARKER = ".mutation_compare"
PYTEST_CONFIG_FILES = ("pytest.ini", "tox.ini", "conftest.py", "setup.cfg", "pyproject.toml")


class Unavailable(Exception):
    """Mutation testing cannot run for these files or in this environment."""


class IntegrityError(Exception):
    """The inputs do not allow a like-for-like comparison."""


# --------------------------------------------------------------------------- git scope


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


CODE_SUFFIXES = (
    ".py",
    ".rs",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".java",
    ".kt",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
    ".sh",
)


def is_test_path(path: str, test_globs: list[str]) -> bool:
    """Explicit --test-glob patterns when given; otherwise files under a `tests/` or `test/` directory.

    Files named `test_*.py` or `*_test.py` outside those directories (tests colocated with the code) are only
    excluded through --test-glob, so a production module such as `test_utils.py` is never dropped by name.
    """
    p = PurePosixPath(path)
    if test_globs:
        return any(p.match(glob) or fnmatch.fnmatch(path, glob) for glob in test_globs)
    return any(part in {"tests", "test"} for part in p.parts[:-1])


def changed_files(base: str, paths: list[str]) -> dict[str, list[int]]:
    """Every file with lines added or modified since merge-base(base, HEAD), relative to cwd."""
    merge_base = git("merge-base", base, "HEAD").strip()
    diff = git("diff", "-U0", "--no-color", "--no-ext-diff", "--relative", merge_base, "--", *paths)
    result: dict[str, set[int]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = None if target == "/dev/null" else target.removeprefix("b/")
        elif line.startswith("@@") and current:
            match = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            start, count = int(match.group(1)), int(match.group(2) or 1)
            result.setdefault(current, set()).update(range(start, start + count))
    for path in git("ls-files", "--others", "--exclude-standard", "--", *paths).splitlines():
        text = Path(path).read_text(errors="replace")
        result[path] = set(range(1, text.count("\n") + 1 + (not text.endswith("\n") and bool(text))))
    return {path: sorted(lines) for path, lines in sorted(result.items()) if lines and Path(path).is_file()}


def line_ranges(lines: list[int]) -> str:
    ranges, start = [], None
    for prev, line in zip([None, *lines], lines):
        if prev is None or line != prev + 1:
            if start is not None:
                ranges.append(f"{start}-{prev}" if prev != start else str(start))
            start = line
    if start is not None:
        ranges.append(f"{start}-{lines[-1]}" if lines[-1] != start else str(start))
    return ",".join(ranges)


def file_hashes(paths) -> dict[str, str]:
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}


# --------------------------------------------------------------------------- engines


@dataclass
class Context:
    changed: dict[str, list[int]]
    tests: list[str]
    pytest_args: list[str]
    runner: list[str]
    work_dir: Path
    max_children: int
    deadline: float

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise IntegrityError("time budget exhausted; rerun with a larger --max-minutes or a smaller --max-mutants")
        return left


class Engine:
    """One mutation tool. list_mutants() and run() must agree on mutant ids."""

    name = "abstract"
    suffixes: tuple[str, ...] = ()
    stub_reason = "this engine is not implemented"

    def time_suite(self, ctx: Context) -> float:
        """Run the focused suite once unmutated; fail if it does not pass. Return seconds."""
        raise Unavailable(self.stub_reason)

    def list_mutants(self, ctx: Context) -> list[dict]:
        """Return every mutant on the changed lines: {id, file, lines, diff}."""
        raise Unavailable(self.stub_reason)

    def run(self, ctx: Context, ids: list[str], timeout_s: float) -> dict[str, str]:
        """Run the current suite against `ids` only and return {id: status}."""
        raise Unavailable(self.stub_reason)


class CargoMutantsEngine(Engine):
    """Rust hook, not implemented. A real implementation would call
    `cargo mutants --in-diff <diff> --list --json` for ids and
    `cargo mutants --in-diff <diff> --file ... --re <id> --json` to run them."""

    name = "cargo-mutants"
    suffixes = (".rs",)
    stub_reason = "the cargo-mutants hook is a stub; Rust mutation comparison is not implemented"


class StrykerEngine(Engine):
    """JS/TS hook, not implemented. A real implementation would pass
    `--mutate <file>:<start>-<end>` per changed range to Stryker and read its JSON report."""

    name = "stryker"
    suffixes = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
    stub_reason = "the Stryker hook is a stub; JS/TS mutation comparison is not implemented"


class MutmutEngine(Engine):
    name = f"mutmut=={MUTMUT_VERSION}"
    suffixes = (".py",)

    def _driver(self, ctx: Context, phase: str, payload: dict, timeout_s: float | None) -> dict:
        request = ctx.work_dir / f"{phase}-request.json"
        response = ctx.work_dir / f"{phase}-response.json"
        response.unlink(missing_ok=True)
        request.write_text(json.dumps(payload))
        cmd = [*ctx.runner, str(Path(__file__).resolve()), "_driver", phase, str(request), str(response)]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_s)
        except FileNotFoundError as error:
            raise Unavailable(f"cannot start the mutmut runner {ctx.runner[0]!r}: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise IntegrityError(
                f"mutmut {phase} exceeded {timeout_s:.0f}s; rerun baseline with a smaller --max-mutants"
            ) from error
        finally:
            self._park_mutants_dir(ctx, phase)
        (ctx.work_dir / f"{phase}.log").write_text(proc.stdout + proc.stderr)
        if not response.exists():
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
            raise Unavailable(f"mutmut {phase} failed (exit {proc.returncode}). Last output:\n{tail}")
        return json.loads(response.read_text())

    @staticmethod
    def _park_mutants_dir(ctx: Context, phase: str) -> None:
        """mutmut writes ./mutants; move it out of the repo into the work dir."""
        source = Path("mutants")
        if source.exists():
            target = ctx.work_dir / f"mutants-{phase}"
            if target.exists() and not (target / MARKER).exists():
                # Never delete what this script did not create, and still take mutmut's output out of the repo.
                parked = Path(tempfile.mkdtemp(prefix=f"mutants-{phase}-", dir=ctx.work_dir))
                shutil.move(str(source), str(parked / "mutants"))
                raise IntegrityError(
                    f"{target} exists and was not created by this script; mutmut output moved to {parked}. "
                    "Choose another --work-dir"
                )
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))
            (target / MARKER).write_text("created by mutation_compare.py\n")

    def _payload(self, ctx: Context) -> dict:
        files = sorted(ctx.changed)
        return {
            "only_mutate": files,
            "source_paths": source_paths(files),
            "tests": [*ctx.tests, *ctx.pytest_args],
            "also_copy": [p for p in (*ctx.tests, *PYTEST_CONFIG_FILES) if Path(p).exists()],
            "changed": ctx.changed,
            "max_children": ctx.max_children,
        }

    def list_mutants(self, ctx):
        return self._driver(ctx, "list", self._payload(ctx), timeout_s=ctx.remaining())["mutants"]

    def run(self, ctx, ids, timeout_s):
        return self._driver(ctx, "run", {**self._payload(ctx), "ids": ids}, timeout_s)["statuses"]

    def time_suite(self, ctx):
        # Import the working tree's code, as mutmut does, not an editable install elsewhere.
        roots = {str(PurePosixPath(r).parent) for r in source_paths(sorted(ctx.changed))}
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([*sorted(roots), os.environ.get("PYTHONPATH", "")])}
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [*ctx.runner, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *ctx.tests, *ctx.pytest_args],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=ctx.remaining(),
            )
        except subprocess.TimeoutExpired as error:
            raise IntegrityError("the unmutated suite did not finish within the budget") from error
        if proc.returncode != 0:
            tail = "\n".join(proc.stdout.splitlines()[-15:])
            raise IntegrityError(f"the suite does not pass before mutation; fix it first:\n{tail}")
        return time.monotonic() - start


ENGINES: list[Engine] = [MutmutEngine(), CargoMutantsEngine(), StrykerEngine()]


def source_paths(files: list[str]) -> list[str]:
    """Top-level package dirs (or root modules) holding the files, src/ layout aware."""
    roots = set()
    for f in files:
        parts = PurePosixPath(f).parts
        if len(parts) == 1:
            roots.add(parts[0])
        elif parts[0] in {"src", "lib", "source"} and len(parts) > 2:
            roots.add("/".join(parts[:2]))
        else:
            roots.add(parts[0])
    return sorted(roots)


def engine_for(changed: dict[str, list[int]]) -> tuple[Engine, dict[str, list[int]], list[str]]:
    """Pick the engine for the changed code files. Returns (engine, its files, changed code files it cannot mutate).

    Only one engine runs per baseline, so a change spanning languages is partial: the caller must not report it
    as a full mutation check.
    """
    by_engine: dict[str, dict[str, list[int]]] = {}
    unsupported = []
    for path, lines in changed.items():
        engine = next((e for e in ENGINES if path.endswith(e.suffixes)), None)
        if engine is not None:
            by_engine.setdefault(engine.name, {})[path] = lines
        elif path.endswith(CODE_SUFFIXES):
            unsupported.append(path)
    chosen = next((e for e in ENGINES if e.name in by_engine), None)
    if chosen is None:
        raise Unavailable(f"no mutation engine for the changed code files: {', '.join(unsupported) or 'none'}")
    skipped = unsupported + [p for name, files in by_engine.items() if name != chosen.name for p in files]
    return chosen, by_engine[chosen.name], sorted(skipped)


# --------------------------------------------------------------------------- commands


def default_runner() -> list[str]:
    project = Path.cwd()
    for directory in (project, *project.parents):
        if (directory / "uv.lock").exists():
            return ["uv", "run", "--project", str(directory), "--with", f"mutmut=={MUTMUT_VERSION}", "python"]
        if (directory / ".git").exists():
            break
    return ["uv", "run", "--no-project", "--with", f"mutmut=={MUTMUT_VERSION}", "--with", "pytest", "python"]


def build_context(args, changed, budget_s: float) -> Context:
    work_dir = Path(args.work_dir or Path(args.out).resolve().parent / "mutation-work").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    tests = args.tests or [t for t in ("tests", "test") if Path(t).is_dir()]
    runner = shlex.split(args.runner) if args.runner else default_runner()
    pytest_args = shlex.split(args.pytest_args or "")
    max_children = args.max_children or os.cpu_count() or 4
    return Context(changed, tests, pytest_args, runner, work_dir, max_children, time.monotonic() + budget_s)


def write_json(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def refuse_existing_mutants_dir() -> None:
    if Path("mutants").exists():
        raise IntegrityError("./mutants already exists; move it away so this run cannot overwrite it")


def cmd_baseline(args) -> int:
    refuse_existing_mutants_dir()
    every_file = changed_files(args.base, args.paths)
    excluded = sorted(p for p in every_file if is_test_path(p, args.test_glob))
    non_code = sorted(p for p in every_file if p not in excluded and not p.endswith(CODE_SUFFIXES))
    changed_all = {p: lines for p, lines in every_file.items() if p not in excluded and p not in non_code}
    record = {
        "status": "ok",
        "base": args.base,
        "merge_base": git("merge-base", args.base, "HEAD").strip(),
        "head": git("rev-parse", "HEAD").strip(),
        "cwd": str(Path.cwd()),
        "changed_lines": changed_all,
        "excluded_as_tests": excluded,
        "ignored_non_code": non_code,
    }
    try:
        engine, changed, skipped = engine_for(changed_all)
    except Unavailable as error:
        if not changed_all:
            write_json(args.out, {**record, "mutants": [], "status": "no_changed_lines"})
            print("No changed production lines: nothing to mutate.")
            return 0
        write_json(args.out, {**record, "status": "unavailable", "reason": str(error)})
        print(f"mutation check unavailable: {error}", file=sys.stderr)
        return 3
    ctx = build_context(args, changed, budget_s=args.max_minutes * 60)
    try:
        suite_s = engine.time_suite(ctx)
        candidates = sorted(engine.list_mutants(ctx), key=lambda m: m["id"])
        if not candidates:
            raise Unavailable("no mutants on the changed lines (comments, imports or declarations only)")
        run_budget_s = min(args.max_minutes * 60 * (1 - SETUP_SHARE_OF_BUDGET), ctx.remaining())
        fits = int(run_budget_s * ctx.max_children / (suite_s + PER_MUTANT_OVERHEAD_S))
        limit = min(fits, args.max_mutants) if args.max_mutants else fits
        if limit < 1:
            raise IntegrityError(
                f"the budget cannot run a single mutant (suite takes {suite_s:.0f}s); raise --max-minutes"
            )
        sampled = len(candidates) > limit
        chosen = (
            sorted(random.Random(args.seed).sample(candidates, limit), key=lambda m: m["id"]) if sampled else candidates
        )
        statuses = engine.run(ctx, [m["id"] for m in chosen], timeout_s=ctx.remaining())
    except Unavailable as error:
        write_json(args.out, {**record, "status": "unavailable", "reason": str(error)})
        print(f"mutation check unavailable: {error}", file=sys.stderr)
        return 3
    for mutant in chosen:
        mutant["status"] = statuses[mutant["id"]]
        mutant["killed"] = mutant["status"] in KILLED_STATUSES
    record.update(
        engine=engine.name,
        tests=ctx.tests,
        pytest_args=ctx.pytest_args,
        runner=ctx.runner,
        skipped_files=skipped,
        production_hashes=file_hashes(changed),
        seed=args.seed,
        sampled=sampled,
        candidate_count=len(candidates),
        max_minutes=args.max_minutes,
        suite_seconds=round(suite_s, 2),
        mutants=chosen,
    )
    if skipped:
        record["status"] = "partial"
        record["reason"] = f"changed code files not mutated: {', '.join(skipped)}"
    write_json(args.out, record)
    killed = sum(m["killed"] for m in chosen)
    for path, lines in changed_all.items():
        print(f"changed {path}:{line_ranges(lines)} ({'mutated' if path in changed else 'NOT mutated'})")
    if excluded:
        print(f"excluded as tests (check none is production code, else pass --test-glob): {', '.join(excluded)}")
    print(
        f"baseline: {killed}/{len(chosen)} mutants killed"
        + (f" (seeded sample {args.seed} of {len(candidates)})" if sampled else "")
    )
    if skipped:
        print(f"mutation check partial: {record['reason']}", file=sys.stderr)
        return 3
    return 0


def cmd_compare(args) -> int:
    refuse_existing_mutants_dir()
    baseline = json.loads(Path(args.baseline).read_text())
    if baseline.get("status") == "unavailable":
        print(f"mutation check unavailable: {baseline['reason']}", file=sys.stderr)
        return 3
    mutants = baseline["mutants"]
    changed = {f: baseline["changed_lines"][f] for f in baseline.get("production_hashes", {})}
    drift = [
        f for f, h in baseline.get("production_hashes", {}).items() if not Path(f).is_file() or file_hashes([f])[f] != h
    ]
    if drift:
        print(f"production code changed since the baseline: {', '.join(drift)}", file=sys.stderr)
        return 2
    report = {
        "baseline": str(Path(args.baseline).resolve()),
        "mutant_ids": [m["id"] for m in mutants],
        "sampled": baseline.get("sampled", False),
        "seed": baseline.get("seed"),
    }
    if mutants:
        args.runner = args.runner or shlex.join(baseline["runner"])
        args.tests = args.tests or baseline["tests"]
        if args.pytest_args is None:
            args.pytest_args = shlex.join(baseline.get("pytest_args", []))
        ctx = build_context(args, changed, budget_s=baseline.get("max_minutes", 20) * 60 * 2)
        engine = next(e for e in ENGINES if e.name == baseline["engine"])
        engine.time_suite(ctx)
        regenerated = {m["id"]: m for m in engine.list_mutants(ctx)}
        mismatched = [m["id"] for m in mutants if regenerated.get(m["id"], {}).get("diff") != m["diff"]]
        if mismatched:
            print(f"mutant ids no longer match the baseline: {', '.join(mismatched[:10])}", file=sys.stderr)
            return 2
        statuses = engine.run(ctx, report["mutant_ids"], timeout_s=ctx.remaining())
    else:
        statuses = {}
    before = {m["id"] for m in mutants if m["killed"]}
    after = {i for i, s in statuses.items() if s in KILLED_STATUSES}
    by_id = {m["id"]: m for m in mutants}
    report.update(
        baseline_killed=len(before),
        new_killed=len(after),
        total=len(mutants),
        statuses=statuses,
        lost=sorted(before - after),
        gained=sorted(after - before),
        survivors=[
            {
                "id": i,
                "file": by_id[i]["file"],
                "lines": by_id[i]["lines"],
                "diff": by_id[i]["diff"],
                "status": statuses[i],
            }
            for i in sorted(set(statuses) - after)
        ],
    )
    write_json(args.out, report)
    print(
        f"killed before: {len(before)}/{len(mutants)}  after: {len(after)}/{len(mutants)}"
        + (f"  (seeded sample, seed {report['seed']})" if report["sampled"] else "")
    )
    for label, ids in (
        ("lost (old suite killed, new misses)", report["lost"]),
        ("gained (new suite kills, old missed)", report["gained"]),
    ):
        if ids:
            print(f"{label}: {', '.join(ids)}")
    for survivor in report["survivors"]:
        print(
            f"\nsurvivor {survivor['id']} ({survivor['file']}:{survivor['lines']}, {survivor['status']})\n"
            f"{survivor['diff']}"
        )
    if len(after) < len(before):
        return 1
    if baseline.get("status") == "partial":
        print(f"mutation check partial: {baseline['reason']}", file=sys.stderr)
        return 3
    return 0


# --------------------------------------------------------------------------- size


def _snapshot_text(rev: str | None, path: str) -> str | None:
    if rev is None:
        file = Path(path)
        return file.read_text(errors="replace") if file.is_file() else None
    proc = subprocess.run(["git", "show", f"{rev}:./{path}"], check=False, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def _units(path: str, text: str | None) -> tuple[dict[str, tuple[str, int, bool]], bool]:
    """Units of a test file: {name: (normalized source, line count, is_test)}, and whether this is approximate.

    Python: every top-level statement (test, fixture, helper, constant, import) is a unit whose line count is its
    AST span including decorators, and a class is split into its methods. Other languages: the whole file is one
    unit and test definitions are found by pattern (approximate).
    """
    if not text:
        return {}, False
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            found: dict[str, tuple[str, int, bool]] = {}
            for index, node in enumerate(tree.body):
                if isinstance(node, ast.ClassDef):
                    methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    items = [(f"{node.name}.{m.name}", m) for m in methods] or [(node.name, node)]
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    items = [(node.name, node)]
                else:
                    items = [(f"<statement {index}>", node)]
                for name, item in items:
                    first = min([item.lineno, *(d.lineno for d in getattr(item, "decorator_list", []))])
                    is_test = isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test")
                    found[name] = (ast.unparse(item), item.end_lineno - first + 1, is_test)
            return found, False
    pattern = re.compile(r"^\s*(#\[test\]|(it|test)\(|func Test|def test)")
    tests = {f"<test {i}>": ("", 0, True) for i, line in enumerate(text.splitlines()) if pattern.match(line)}
    return {"<file>": (text, len(text.splitlines()), False), **tests}, True


def cmd_size(args) -> int:
    """Lines and test definitions of the test-file units a snapshot added or changed since the merge base.

    A unit counts in full when its source matches no unit of the merge-base version of the file, so an edited
    test costs its whole length, a restored or untouched one costs nothing, and helpers and fixtures count too.
    """
    merge_base = git("merge-base", args.base, "HEAD").strip()
    rev = None if args.rev == "worktree" else args.rev
    target = [] if rev is None else [rev]
    paths = git("diff", "--no-renames", "--name-only", "--relative", merge_base, *target, "--", *args.paths).split()
    if rev is None:
        paths += git("ls-files", "--others", "--exclude-standard", "--", *args.paths).split()
    files, approximate = {}, False
    for path in sorted(set(paths)):
        now, rough = _units(path, _snapshot_text(rev, path))
        before, _ = _units(path, _snapshot_text(merge_base, path))
        old_sources = {source for source, _, _ in before.values()}
        changed = {name: unit for name, unit in now.items() if rough or unit[0] not in old_sources}
        approximate |= rough and bool(now)
        if changed:
            files[path] = {
                "lines": sum(span for _, span, _ in changed.values()),
                "tests": sorted(name for name, (_, _, is_test) in changed.items() if is_test),
            }
    record = {
        "merge_base": merge_base,
        "rev": args.rev,
        "paths": sorted(args.paths),
        "files": files,
        "tests": sum(len(f["tests"]) for f in files.values()),
        "lines": sum(f["lines"] for f in files.values()),
        "approximate": approximate,
    }
    write_json(args.out, record)
    print(
        f"{args.rev}: {record['tests']} test definitions, {record['lines']} lines over {len(files)} files"
        + (" (approximate: non-Python tests)" if approximate else "")
    )
    if not args.against:
        return 0
    previous = json.loads(Path(args.against).read_text())
    if previous["paths"] != record["paths"] or previous["merge_base"] != merge_base:
        print("size --against: the saved count used other paths or another merge base", file=sys.stderr)
        return 2
    smaller = record["tests"] < previous["tests"] and record["lines"] < previous["lines"]
    print(
        f"session suite: {previous['tests']} tests, {previous['lines']} lines -> "
        + ("strictly smaller" if smaller else "NOT strictly smaller: BLOCKED")
    )
    return 0 if smaller else 1


# --------------------------------------------------------------------------- mutmut driver
# Runs inside the repo's environment (with mutmut installed), invoked by MutmutEngine.


def _driver(phase: str, request_path: str, response_path: str) -> None:
    request = json.loads(Path(request_path).read_text())
    from mutmut import configuration

    original_reader = configuration._config_reader
    overrides = {
        "source_paths": request["source_paths"],
        "only_mutate": request["only_mutate"],
        "pytest_add_cli_args_test_selection": request["tests"],
        "also_copy": request["also_copy"],
        "use_setproctitle": False,
        "mutate_only_covered_lines": False,
        "type_check_command": [],
    }

    def reader():
        base = original_reader()
        return lambda key, default: overrides[key] if key in overrides else base(key, default)

    configuration._config_reader = reader
    configuration.reset_config()

    from mutmut import __main__ as mm
    from mutmut.mutation.data import SourceFileMutationData

    if phase == "list":
        os.makedirs("mutants", exist_ok=True)
        mm.copy_src_dir()
        mm.copy_also_copy_files()
        mm.setup_source_paths()
        mm.create_mutants(request["max_children"])
        mutants = []
        for path, lines in request["changed"].items():
            data = SourceFileMutationData(path=path)
            data.load()
            changed = set(lines)
            for mutant_id in data.exit_code_by_key:
                mutant_lines, diff = _mutant_lines(mutant_id, path)
                if changed & set(mutant_lines):
                    mutants.append({"id": mutant_id, "file": path, "lines": mutant_lines, "diff": diff})
        Path(response_path).write_text(json.dumps({"mutants": mutants}))
    elif phase == "run":
        ids = request["ids"]
        mm._run(ids, request["max_children"])
        statuses = {}
        for path in request["changed"]:
            data = SourceFileMutationData(path=path)
            data.load()
            for mutant_id, code in data.exit_code_by_key.items():
                if mutant_id in ids:
                    statuses[mutant_id] = mm.status_by_exit_code[code]
        missing = sorted(set(ids) - set(statuses))
        if missing:
            raise SystemExit(f"mutmut produced no result for: {', '.join(missing)}")
        Path(response_path).write_text(json.dumps({"statuses": statuses}))


def _mutant_lines(mutant_id: str, path: str) -> tuple[list[int], str]:
    """Source lines a mutant changes, from mutmut's own function diff."""
    import ast
    import difflib

    import libcst as cst
    from mutmut.mutation.diff_apply import get_diff_for_mutant, read_functions_from_index
    from mutmut.utils.format_utils import orig_function_and_class_names_from_key

    original, mutated = read_functions_from_index(mutant_id, path)
    render = [cst.Module(body=[f.with_changes(leading_lines=[])]).code.splitlines() for f in (original, mutated)]
    function_name, class_name = orig_function_and_class_names_from_key(mutant_id)
    tree = ast.parse(Path(path).read_text())
    scope = tree.body
    if class_name:
        scope = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function_name)
    first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    lines = set()
    for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, *render, autojunk=False).get_opcodes():
        if tag != "equal":
            lines.update(range(first + i1, first + max(i2, i1 + 1)))
    return sorted(lines), get_diff_for_mutant(mutant_id, path=path)


# --------------------------------------------------------------------------- CLI


def positive(kind):
    def parse(text: str):
        value = kind(text)
        if value <= 0:
            raise argparse.ArgumentTypeError(f"must be positive, got {text}")
        return value

    return parse


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["_driver"]:
        _driver(*argv[1:4])
        return 0
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", required=True, help="JSON result file (keep it outside the repo)")
    common.add_argument("--tests", nargs="*", help="focused test paths for the touched package (default: tests/)")
    common.add_argument(
        "--pytest-args",
        help="extra pytest arguments for every run, e.g. '--deselect tests/x.py::test_y'; saved in the baseline and "
        "reused by compare. Report every deselection: it weakens the baseline",
    )
    common.add_argument("--runner", help="command prefix that runs python in the repo env with mutmut installed")
    common.add_argument("--work-dir", help="scratch dir for mutmut state (default: next to --out)")
    common.add_argument("--max-children", type=int, help="parallel mutant workers (default: CPU count)")
    b = sub.add_parser("baseline", parents=[common])
    b.add_argument("--base", default="origin/main", help="target branch; the merge base defines the session")
    b.add_argument("--paths", nargs="*", default=[], help="limit the diff to these paths")
    b.add_argument("--max-minutes", type=positive(float), default=20)
    b.add_argument("--max-mutants", type=positive(int))
    b.add_argument(
        "--test-glob",
        action="append",
        default=[],
        help="glob of test files to exclude from mutation (repeatable; replaces the default heuristic)",
    )
    b.add_argument("--seed", type=int, default=DEFAULT_SEED)
    c = sub.add_parser("compare", parents=[common])
    c.add_argument("--baseline", required=True)
    z = sub.add_parser("size")
    z.add_argument("--base", default="origin/main")
    z.add_argument("--paths", nargs="+", required=True, help="test dirs and helper/fixture/data paths, same both runs")
    z.add_argument("--rev", default="worktree", help="'worktree' (includes untracked files) or a git revision")
    z.add_argument("--out", required=True)
    z.add_argument("--against", help="saved size JSON of the session suite; exit 1 unless strictly smaller")
    args = parser.parse_args(argv)
    commands = {"baseline": cmd_baseline, "compare": cmd_compare, "size": cmd_size}
    try:
        return commands[args.command](args)
    except IntegrityError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
