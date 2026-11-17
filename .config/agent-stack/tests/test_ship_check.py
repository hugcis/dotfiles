import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


STACK = Path(__file__).resolve().parents[1]
SHIP_CHECK = STACK / "bin" / "ship-check"
SHIP_GATE = STACK / "hooks" / "ship_check_gate.py"
PASS_CMD = f"{sys.executable} -c 'import sys; sys.exit(0)'"
FAIL_CMD = f"{sys.executable} -c 'import sys; sys.exit(7)'"


def git(repo: Path, *args: str, input: str | None = None) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    identity = ["-c", "user.email=t@example.invalid", "-c", "user.name=Test User"]
    result = subprocess.run(
        ["git", *identity, *args],
        cwd=repo,
        input=input,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-F", "-", input=message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    write(repo / "app.py", "VALUE = 1\n")
    write(repo / "tests" / "test_app.py", "def test_placeholder():\n    assert True\n")
    commit_all(repo, "base\n")
    git(repo, "checkout", "-qb", "feature")
    return repo


def run_ship(repo: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIP_CHECK), "--base", "main", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
    )


def receipts(home: Path) -> list[Path]:
    return sorted((home / ".local" / "state" / "ship-check").glob("*/*.json"))


def run_hook(repo: Path, home: Path, payload: dict, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIP_GATE)],
        cwd=cwd or repo,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
    )


def bash_payload(command: str, repo: Path, *, tool_name: str = "file_system.bash", top_level_cwd: bool = False) -> dict:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    if top_level_cwd:
        payload["cwd"] = str(repo)
    else:
        payload["tool_input"]["cwd"] = str(repo)
    return payload


def denied(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "deny"
    assert "reason" in payload
    assert "message" not in payload
    return payload


def allowed(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_clean_branch_passes_records_test_command_and_writes_receipt(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 2\n")
    sha = commit_all(repo, "change value\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "attribution: PASS" in result.stdout
    assert "size: PASS" in result.stdout
    assert "working_docs: PASS" in result.stdout
    assert "tests: PASS" in result.stdout
    receipt_path = receipts(home)[0]
    receipt = json.loads(receipt_path.read_text())
    assert receipt["sha"] == sha
    assert receipt["overall"] == "pass"
    assert receipt["checks"]["tests"]["command"] == PASS_CMD


def test_ai_attribution_in_commit_message_fails(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 3\n")
    commit_all(repo, "change value\n\nCo-Authored-By: Vibe Agent <agent@example.invalid>\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 1
    assert "attribution: FAIL" in result.stdout
    assert "Co-Authored-By" in result.stdout


def test_oversized_production_diff_fails_without_size_justification(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "".join(f"VALUE_{i} = {i}\n" for i in range(601)))
    commit_all(repo, "large change\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 1
    assert "size: FAIL" in result.stdout
    assert "production lines 602" in result.stdout


def test_oversized_test_diff_reports_tests_but_does_not_trip_the_production_gate(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "tests" / "test_large.py", "".join(f"def test_{i}():\n    assert True\n" for i in range(301)))
    commit_all(repo, "large test change\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "size: PASS" in result.stdout
    assert "production lines 0, tests 602" in result.stdout


def test_size_justification_trailer_allows_an_oversized_production_diff(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "".join(f"VALUE_{i} = {i}\n" for i in range(601)))
    commit_all(repo, "large change\n\nSize-justification: generated fixture table kept together\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "size: PASS" in result.stdout


def test_working_doc_added_on_the_range_fails(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "docs" / "plans" / "feature-plan.md", "temporary plan\n")
    commit_all(repo, "add temporary plan\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 1
    assert "working_docs: FAIL" in result.stdout
    assert "docs/plans/feature-plan.md" in result.stdout


def test_test_command_failure_fails_but_missing_command_is_explicitly_skipped(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 4\n")
    commit_all(repo, "change value\n")

    failed = run_ship(repo, home, "--test-cmd", FAIL_CMD)
    skipped = run_ship(repo, tmp_path / "home-skip")

    assert failed.returncode == 1
    assert "tests: FAIL" in failed.stdout
    assert "exit code 7" in failed.stdout
    assert skipped.returncode == 0, skipped.stdout + skipped.stderr
    assert "tests: SKIPPED" in skipped.stdout


def test_noop_test_command_is_rejected_as_a_gate_bypass(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 5\n")
    commit_all(repo, "change value\n")

    result = run_ship(repo, home, "--test-cmd", "true")

    assert result.returncode == 1
    assert "tests: FAIL" in result.stdout
    assert "no-op" in result.stdout


def test_ship_check_toml_supplies_the_test_command(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "ship-check.toml", f'test-cmd = "{PASS_CMD}"\n')
    write(repo / "app.py", "VALUE = 6\n")
    commit_all(repo, "change value\n")

    result = run_ship(repo, home)

    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(receipts(home)[0].read_text())
    assert receipt["checks"]["tests"]["command"] == PASS_CMD


def test_gate_denies_without_receipt_allows_matching_receipt_and_denies_after_amend(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 7\n")
    commit_all(repo, "change value\n")

    first_denial = denied(run_hook(repo, home, bash_payload("git push origin HEAD", repo)))
    assert "receipt" in first_denial["reason"]
    passed = run_ship(repo, home, "--test-cmd", PASS_CMD)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    allowed(run_hook(repo, home, bash_payload("git push origin HEAD", repo)))

    git(repo, "commit", "--amend", "-F", "-", input="same tree, new commit\n")

    second_denial = denied(run_hook(repo, home, bash_payload("git push origin HEAD", repo)))
    assert "receipt" in second_denial["reason"]


def test_gate_guards_gh_pr_create_and_ready_and_process_start_payloads(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 8\n")
    commit_all(repo, "change value\n")

    denied(run_hook(repo, home, bash_payload("gh pr create --fill", repo)))
    denied(run_hook(repo, home, bash_payload("gh pr ready", repo, tool_name="process_start")))
    denied(run_hook(repo, home, bash_payload("gh pr merge 123", repo)))



@pytest.mark.parametrize("tool_name", ["bash", "file_system.bash", "process_start", "process.start"])
def test_gate_guards_any_command_bearing_shell_tool_name(tmp_path, tool_name):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 9\n")
    commit_all(repo, "change value\n")

    denial = denied(run_hook(repo, home, bash_payload("git push origin HEAD", repo, tool_name=tool_name)))

    assert "receipt" in denial["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "git -C . push origin x",
        "/usr/bin/git push",
        "command git push",
        "env FOO=1 git push",
        "FOO=1 git push",
        "git  push",
        "git -c x=y push",
        "exec git push",
        "git --git-dir=.git --work-tree=. push",
        "true && git push",
        "true; gh pr merge 123",
        "true\ngh pr create --fill",
    ],
)
def test_gate_parses_guarded_command_forms_in_shell_segments(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 10\n")
    commit_all(repo, "change value\n")

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "receipt" in denial["reason"]


def test_gate_does_not_guard_echoed_command_text(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 11\n")
    commit_all(repo, "change value\n")

    allowed(run_hook(repo, home, bash_payload("echo git push", repo)))


def test_gate_uses_top_level_cwd_before_process_cwd(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 12\n")
    commit_all(repo, "change value\n")
    outside = tmp_path / "outside"
    outside.mkdir()

    denial = denied(run_hook(repo, home, bash_payload("git push origin HEAD", repo, top_level_cwd=True), cwd=outside))

    assert "receipt" in denial["reason"]
