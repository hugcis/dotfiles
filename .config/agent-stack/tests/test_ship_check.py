import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


STACK = Path(__file__).resolve().parents[1]
SHIP_CHECK = STACK / "bin" / "ship-check"
SHIP_GATE = STACK / "hooks" / "ship_check_gate.py"
PASS_CMD = f"{sys.executable} -c 'import sys; sys.exit(0)'"


def git(repo: Path, *args: str, input: str | None = None, check: bool = True) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    identity = ["-c", "user.email=t@example.invalid", "-c", "user.name=Test User"]
    result = subprocess.run(
        ["git", *identity, *args],
        cwd=repo,
        input=input,
        text=True,
        capture_output=True,
        check=check,
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


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
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


def run_hook(repo: Path, home: Path, payload: dict, *, cwd: Path | None = None, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIP_GATE)],
        cwd=cwd or repo,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home), **(extra_env or {})},
    )


def bash_payload(command: str, repo: Path, *, tool_name: str = "file_system.bash") -> dict:
    return {"tool_name": tool_name, "tool_input": {"command": command, "cwd": str(repo)}}


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


def fake_gh(directory: Path, *, head: str, rollup: list[dict] | None = None, exit_code: int = 0) -> Path:
    bin_dir = directory / "bin"
    bin_dir.mkdir()
    script = bin_dir / "gh"
    if exit_code:
        script.write_text(f"#!/bin/sh\necho gh failed >&2\nexit {exit_code}\n")
    else:
        body = json.dumps({"headRefOid": head, "statusCheckRollup": rollup or []})
        script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{body}'\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def test_ship_check_is_local_prefight_only_and_writes_no_receipt(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 2\n")
    commit_all(repo, "change value\n")

    result = run_ship(repo, home, "--test-cmd", PASS_CMD)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests: PASS" in result.stdout
    assert "receipt:" not in result.stdout
    assert not (home / ".local" / "state" / "ship-check").exists()


def test_push_gate_reruns_inline_checks_and_ignores_forged_receipts(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 3\n")
    sha = commit_all(repo, "change value\n\nCo-Authored-By: Vibe Agent <agent@example.invalid>\n")
    forged = home / ".local" / "state" / "ship-check" / "repo-forged" / f"{sha}.json"
    write(forged, json.dumps({"overall": "pass", "sha": sha}))

    denial = denied(run_hook(repo, home, bash_payload("git push origin HEAD", repo)))

    assert "attribution" in denial["reason"]
    assert "receipt" not in denial["reason"].lower()


def test_push_gate_allows_clean_inline_checks_without_receipt(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 4\n")
    commit_all(repo, "change value\n")

    allowed(run_hook(repo, home, bash_payload("git push origin HEAD", repo)))


@pytest.mark.parametrize(
    "command",
    ["cd ../other && git push", "git -C ../other push", "git --git-dir=../other/.git --work-tree=../other push"],
)
def test_b4_push_checks_the_repo_targeted_by_cd_or_git_directory_options(tmp_path, command):
    caller = make_repo(tmp_path, "caller")
    other = make_repo(tmp_path, "other")
    home = tmp_path / "home"
    write(other / "app.py", "VALUE = 5\n")
    commit_all(other, "bad\n\nGenerated by Vibe\n")

    denial = denied(run_hook(caller, home, bash_payload(command, caller)))

    assert "attribution" in denial["reason"]


def test_b4_uncertain_push_target_denies_with_actionable_reason(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload("git --git-dir=.git push", repo)))

    assert "run the push from inside the repo" in denial["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "sudo git push",
        "doas git push",
        "env FOO=1 git push",
        "nohup git push",
        "timeout 5 git push",
        "stdbuf -oL git push",
        "nice -n 10 git push",
        "command git push",
        "exec git push",
        "( git push )",
        "{ git push; }",
    ],
)
def test_h2_wrappers_still_reach_inline_push_checks(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 6\n")
    commit_all(repo, "bad\n\nGenerated by Vibe\n")

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "attribution" in denial["reason"]


@pytest.mark.parametrize(
    "command",
    [
        'echo "git push" | bash',
        'bash <<< "git push"',
        'cat <<EOF | bash\ngit push\nEOF',
        'printf "%s" "git push" | xargs sh -c',
        'xargs git push',
        'ssh host git push',
    ],
)
def test_h2_unreadable_shell_feeds_and_remote_pushes_fail_closed(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "unreadable" in denial["reason"] or "run the push from inside the repo" in denial["reason"]


def test_h3_pr_ready_with_no_ci_denies_even_when_inline_checks_pass(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 7\n")
    head = commit_all(repo, "change value\n")
    gh_bin = fake_gh(tmp_path, head=head, rollup=[])

    denial = denied(run_hook(repo, home, bash_payload("gh pr ready", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))

    assert "status checks" in denial["reason"]
    assert head in denial["reason"]


def test_pr_merge_denies_when_gh_fails(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    gh_bin = fake_gh(tmp_path, head="unused", exit_code=1)

    denial = denied(run_hook(repo, home, bash_payload("gh pr merge", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))

    assert "gh pr view" in denial["reason"]


def test_pr_ready_allows_when_every_check_succeeds_for_current_head(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 8\n")
    head = commit_all(repo, "change value\n")
    gh_bin = fake_gh(
        tmp_path,
        head=head,
        rollup=[{"name": "ci", "conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    allowed(run_hook(repo, home, bash_payload("gh pr ready", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))


def test_gh_pr_create_runs_only_inline_checks_not_ci(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    write(repo / "app.py", "VALUE = 9\n")
    commit_all(repo, "change value\n")
    gh_bin = fake_gh(tmp_path, head="would-fail-if-called", exit_code=1)

    allowed(run_hook(repo, home, bash_payload("gh pr create --draft", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))
