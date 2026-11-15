"""Contract tests for mutation_compare.py, run through its CLI on throwaway git repos.

Run: uv run --no-project --with pytest pytest scripts/mutation_compare_test.py -q
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("mutation_compare.py")

needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required to run mutmut")

BASE_CALC = """\
def add(a, b):
    return a + b


def sub(a, b):
    return a - b
"""

BRANCH_CALC = (
    BASE_CALC
    + """

def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
"""
)

UNTRACKED_SCALE = """\
def scale(x, k):
    return x * k
"""

STRONG_SUITE = """\
from toy.calc import add, clamp, sub
from toy.scale import scale


def test_add():
    assert add(2, 3) == 5


def test_sub():
    assert sub(5, 3) == 2


def test_clamp_below():
    assert clamp(-1, 0, 10) == 0


def test_clamp_above():
    assert clamp(11, 0, 10) == 10


def test_clamp_inside():
    assert clamp(4, 0, 10) == 4


def test_scale():
    assert scale(3, 4) == 12
"""

REWRITTEN_STRONG_SUITE = """\
import pytest

from toy.calc import clamp
from toy.scale import scale


@pytest.mark.parametrize("x, expected", [(-1, 0), (11, 10), (4, 4)])
def test_clamp_keeps_value_in_range(x, expected):
    assert clamp(x, 0, 10) == expected


def test_scale_multiplies():
    assert scale(3, 4) == 12
"""

WEAK_SUITE = """\
from toy.calc import clamp


def test_clamp_inside():
    assert clamp(4, 0, 10) == 4
"""


def git(repo, *args):
    """Fixture repos are hermetic: the developer's global and system git config never applies."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    identity = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", *identity, *args], cwd=repo, env=env, check=True, capture_output=True)


def run_cli(repo, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=600,
    )


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture(scope="module")
def branch_repo(tmp_path_factory):
    """A `feat` branch off `main`: clamp() added to calc.py, scale.py new and uncommitted."""
    repo = tmp_path_factory.mktemp("toy")
    # No pytest `pythonpath`: the script itself must make the working tree's src/ importable.
    write(repo / "pyproject.toml", '[project]\nname = "toy"\nversion = "0"\n')
    write(repo / "src/toy/__init__.py", "")
    write(repo / "src/toy/calc.py", BASE_CALC)
    write(repo / "tests/test_calc.py", STRONG_SUITE.replace("from toy.scale import scale\n", ""))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "feat")
    write(repo / "src/toy/calc.py", BRANCH_CALC)
    git(repo, "commit", "-qam", "clamp")
    write(repo / "src/toy/scale.py", UNTRACKED_SCALE)
    write(repo / "tests/test_calc.py", STRONG_SUITE)
    return repo


@pytest.fixture(scope="module")
def baseline(branch_repo, tmp_path_factory):
    out = tmp_path_factory.mktemp("out") / "baseline.json"
    result = run_cli(branch_repo, "baseline", "--base", "main", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(out.read_text())


@pytest.fixture
def repo_copy(branch_repo, tmp_path):
    copy = tmp_path / "repo"
    shutil.copytree(branch_repo, copy)
    return copy


@needs_uv
def test_baseline_mutates_only_changed_production_lines(baseline):
    changed = {path: set(lines) for path, lines in baseline["changed_lines"].items()}
    assert set(changed) == {"src/toy/calc.py", "src/toy/scale.py"}
    assert changed["src/toy/calc.py"] == set(range(7, 15))
    assert baseline["mutants"]
    for mutant in baseline["mutants"]:
        assert set(mutant["lines"]) <= changed[mutant["file"]], mutant
    assert {m["file"] for m in baseline["mutants"]} == set(changed)


@needs_uv
@pytest.mark.parametrize(
    "suite, exit_code",
    [
        pytest.param(REWRITTEN_STRONG_SUITE, 0, id="equal-strength-rewrite-passes"),
        pytest.param(WEAK_SUITE, 1, id="weaker-rewrite-fails"),
    ],
)
def test_compare_judges_the_new_suite_on_the_baseline_mutant_ids(baseline, repo_copy, tmp_path, suite, exit_code):
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps(baseline))
    write(repo_copy / "tests/test_calc.py", suite)
    out = tmp_path / "compare.json"

    result = run_cli(repo_copy, "compare", "--baseline", str(baseline_file), "--out", str(out))

    assert result.returncode == exit_code, result.stdout + result.stderr
    report = json.loads(out.read_text())
    assert sorted(report["mutant_ids"]) == sorted(m["id"] for m in baseline["mutants"])
    assert report["baseline_killed"] == sum(m["killed"] for m in baseline["mutants"])
    weaker = exit_code == 1
    assert (report["new_killed"] < report["baseline_killed"]) == weaker
    assert bool(report["lost"]) == weaker, "only a weaker suite names mutants it no longer kills"
    assert set(report["lost"]) <= set(report["mutant_ids"])


@needs_uv
def test_compare_refuses_when_production_code_changed_since_baseline(baseline, repo_copy, tmp_path):
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps(baseline))
    write(repo_copy / "src/toy/scale.py", UNTRACKED_SCALE.replace("x * k", "k * x"))

    result = run_cli(repo_copy, "compare", "--baseline", str(baseline_file), "--out", str(tmp_path / "c.json"))

    assert result.returncode == 2
    assert "src/toy/scale.py" in result.stderr


@needs_uv
def test_over_budget_baseline_draws_a_reproducible_seeded_sample(baseline, branch_repo, tmp_path):
    """Two baselines with the same seed sample the same ids, so compare stays like for like."""
    runs = []
    for name in ("a", "b"):
        out = tmp_path / f"{name}.json"
        result = run_cli(
            branch_repo, "baseline", "--base", "main", "--max-mutants", "2", "--seed", "7", "--out", str(out)
        )
        assert result.returncode == 0, result.stdout + result.stderr
        runs.append(json.loads(out.read_text()))

    first, second = runs
    assert first["sampled"] is True and first["seed"] == 7
    assert first["candidate_count"] == len(baseline["mutants"]) > 2
    assert len(first["mutants"]) == 2
    assert [m["id"] for m in first["mutants"]] == [m["id"] for m in second["mutants"]]


def feature_branch(repo, base_files, branch_files):
    for path, text in base_files.items():
        write(repo / path, text)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "feat")
    for path, text in branch_files.items():
        write(repo / path, text)
    return repo


@pytest.mark.parametrize(
    "branch_files, status, reason",
    [
        pytest.param(
            {"src/lib.rs": "pub fn one() -> i32 { 1 }\npub fn two() -> i32 { 2 }\n"},
            "unavailable",
            "cargo-mutants",
            id="rust-only-change",
        ),
        pytest.param(
            {"src/toy/calc.py": BRANCH_CALC, "web/thing.js": "export const two = () => 2;\n"},
            "partial",
            "web/thing.js",
            id="mixed-python-and-js-change",
        ),
        pytest.param(
            {"src/toy/calc.py": BASE_CALC + "\n# a comment only\n"},
            "unavailable",
            "no mutants",
            id="changed-lines-without-mutants",
        ),
    ],
)
@needs_uv
def test_incomplete_mutation_scope_never_reports_success(tmp_path, branch_files, status, reason):
    """A baseline that cannot mutate every changed code line exits 3, so the skill reports the check unavailable."""
    repo = feature_branch(
        tmp_path / "repo",
        {
            "pyproject.toml": '[project]\nname = "toy"\nversion = "0"\n',
            "src/toy/__init__.py": "",
            "src/toy/calc.py": BASE_CALC,
            "src/lib.rs": "pub fn one() -> i32 { 1 }\n",
            "tests/test_calc.py": STRONG_SUITE.replace("from toy.scale import scale\n", "")
            .replace("from toy.calc import add, clamp, sub", "from toy.calc import add, sub")
            .split("def test_clamp_below")[0],
        },
        branch_files,
    )
    out = tmp_path / "baseline.json"

    result = run_cli(repo, "baseline", "--base", "main", "--out", str(out))

    assert result.returncode == 3, result.stdout + result.stderr
    report = json.loads(out.read_text())
    assert report["status"] == status
    assert reason in report["reason"]


@needs_uv
def test_scope_keeps_production_named_like_tests_and_ignores_non_code(tmp_path):
    """`src/toy/test_utils.py` is production code and is mutated; a README change is not a reason to stop."""
    repo = feature_branch(
        tmp_path / "repo",
        {
            "pyproject.toml": '[project]\nname = "toy"\nversion = "0"\n',
            "src/toy/__init__.py": "",
            "README.md": "x\n",
            "tests/test_utils_use.py": "from toy.test_utils import double\n\n\ndef test_double():\n"
            "    assert double(2) == 4\n",
        },
        {"src/toy/test_utils.py": "def double(x):\n    return x * 2\n", "README.md": "y\n"},
    )
    out = tmp_path / "baseline.json"

    result = run_cli(repo, "baseline", "--base", "main", "--out", str(out))

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(out.read_text())
    assert list(report["changed_lines"]) == ["src/toy/test_utils.py"]
    assert report["ignored_non_code"] == ["README.md"]
    assert {m["file"] for m in report["mutants"]} == {"src/toy/test_utils.py"}

    readme_only = feature_branch(tmp_path / "docs", {"README.md": "x\n"}, {"README.md": "y\n"})
    docs = run_cli(readme_only, "baseline", "--base", "main", "--out", str(tmp_path / "docs.json"))

    assert docs.returncode == 0, docs.stderr
    assert json.loads((tmp_path / "docs.json").read_text())["status"] == "no_changed_lines"


@needs_uv
def test_unowned_work_dir_is_never_deleted_and_the_repo_is_left_clean(branch_repo, tmp_path):
    work = tmp_path / "work"
    (work / "mutants-list").mkdir(parents=True)
    (work / "mutants-list" / "precious.txt").write_text("user data")

    result = run_cli(
        branch_repo, "baseline", "--base", "main", "--work-dir", str(work), "--out", str(tmp_path / "b.json")
    )

    assert result.returncode == 2
    assert (work / "mutants-list" / "precious.txt").read_text() == "user data"
    assert not (branch_repo / "mutants").exists()


@pytest.mark.parametrize("flag", ["--max-minutes", "--max-mutants"])
def test_non_positive_budget_is_rejected(tmp_path, flag):
    """A zero budget would sample zero mutants and pass vacuously."""
    result = run_cli(tmp_path, "baseline", "--base", "main", flag, "0", "--out", str(tmp_path / "b.json"))

    assert result.returncode == 2
    assert "must be positive" in result.stderr


def test_size_counts_changed_test_definitions_and_lines_and_gates_strict_shrink(tmp_path):
    """Session suite (HEAD) vs rebuilt worktree over the same paths: new and edited tests count, untouched ones do not."""
    old_file = "def test_kept():\n    assert True\n\n\ndef test_edited():\n    assert 1\n"
    session_file = (
        "import pytest\n\n\n@pytest.mark.parametrize('x', [1, 2])\ndef test_new(x):\n    assert x\n\n\n"
        "class TestGroup:\n    def test_method(self):\n        assert True\n"
    )
    repo = feature_branch(tmp_path / "repo", {"tests/test_old.py": old_file}, {})
    write(repo / "tests/test_old.py", old_file.replace("assert 1", "assert 2"))
    write(repo / "tests/test_session.py", session_file)
    write(repo / "tests/helpers.py", "VALUE = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "session tests")
    session = tmp_path / "session.json"

    first = run_cli(repo, "size", "--base", "main", "--paths", "tests", "--rev", "HEAD", "--out", str(session))

    assert first.returncode == 0, first.stderr
    counted = json.loads(session.read_text())
    assert counted["tests"] == 3  # test_edited, test_new, TestGroup.test_method; test_kept is untouched
    # Statement spans, blank lines excluded: test_edited 2, import 1, test_new 3 (with decorator), test_method 2,
    # helpers.VALUE 1.
    assert counted["lines"] == 2 + 1 + 3 + 2 + 1

    (repo / "tests/test_session.py").unlink()
    (repo / "tests/helpers.py").unlink()
    write(repo / "tests/test_old.py", old_file)  # restored from the merge base: no longer counted
    write(repo / "tests/test_rebuilt.py", "def test_rebuilt():\n    assert True\n")
    rebuilt = run_cli(
        repo,
        "size",
        "--base",
        "main",
        "--paths",
        "tests",
        "--out",
        str(tmp_path / "new.json"),
        "--against",
        str(session),
    )
    write(
        repo / "tests/test_rebuilt.py",
        "def test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n\n\ndef test_c():\n    assert 3\n",
    )
    same_size = run_cli(
        repo,
        "size",
        "--base",
        "main",
        "--paths",
        "tests",
        "--out",
        str(tmp_path / "new2.json"),
        "--against",
        str(session),
    )

    assert rebuilt.returncode == 0, rebuilt.stdout + rebuilt.stderr
    assert json.loads((tmp_path / "new.json").read_text())["tests"] == 1
    assert same_size.returncode == 1, "three tests against three must not count as shrinking"
    assert "BLOCKED" in same_size.stdout
