import json
import os
import re
import shutil
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


def fake_gh(directory: Path, *, head: str, rollup: list[dict] | None = None, exit_code: int = 0, extra: dict | None = None) -> Path:
    bin_dir = directory / "bin"
    bin_dir.mkdir()
    script = bin_dir / "gh"
    if exit_code:
        script.write_text(f"#!/bin/sh\necho gh failed >&2\nexit {exit_code}\n")
    else:
        body = json.dumps({"headRefOid": head, "statusCheckRollup": rollup or [], **(extra or {})})
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


def test_n1_push_refspec_source_is_checked_not_just_head(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    git(repo, "checkout", "-qb", "bad")
    write(repo / "app.py", "VALUE = 10\n")
    commit_all(repo, "bad branch\n\nGenerated by Vibe\n")
    git(repo, "checkout", "feature")
    write(repo / "app.py", "VALUE = 11\n")
    commit_all(repo, "clean branch\n")

    denial = denied(run_hook(repo, home, bash_payload("git push origin bad:refs/heads/review", repo)))

    assert "attribution" in denial["reason"]


@pytest.mark.parametrize("command", ["git push --all", "git push --mirror", "git push --tags", "git push --follow-tags"])
def test_n1_ambiguous_push_modes_are_denied(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "ambiguous" in denial["reason"]


def test_n1_unresolvable_push_source_is_denied(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload("git push origin no_such_ref:review", repo)))

    assert "unresolvable" in denial["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "git commit --allow-empty -m x && git push",
        "git merge main && git push",
        "git rebase main && gh pr ready",
        "git checkout -b tmp && gh pr merge",
        "git stash pop && gh pr create --draft",
    ],
)
def test_n2_state_mutation_before_publication_is_denied(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "as its own tool call" in denial["reason"]


def test_n3_gh_pr_ready_for_number_passes_repo_and_number_to_gh_and_allows_nonlocal_head(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    gh_bin = tmp_path / "bin"
    gh_bin.mkdir()
    seen = tmp_path / "gh-args.txt"
    script = gh_bin / "gh"
    git(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")
    pr_head = git(repo, "rev-parse", "HEAD")
    body = json.dumps({
        "headRefOid": pr_head,
        "statusCheckRollup": [{"__typename": "CheckRun", "name": "ci", "conclusion": "SUCCESS"}],
        "url": "https://github.com/owner/repo/pull/123",
        "headRepository": {"nameWithOwner": "owner/repo"},
    })
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" > {seen}\nprintf '%s\\n' '{body}'\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    allowed(run_hook(repo, home, bash_payload("GH_REPO=owner/repo gh pr ready 123", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))

    args = seen.read_text()
    assert "123" in args
    assert "--repo owner/repo" in args


def test_n3_gh_pr_ready_without_repo_identity_is_denied(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload("gh pr ready 123", repo)))

    assert "PR identity is unclear" in denial["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "gh api -X PATCH repos/o/r/pulls/1 -f title=x",
        "gh api graphql -f query='mutation { closePullRequest(input:{pullRequestId:\"x\"}) { clientMutationId } }'",
        "curl -X POST https://api.github.com/repos/o/r/pulls/1/merge",
        "wget --method=DELETE https://api.github.com/repos/o/r/pulls/1",
    ],
)
def test_n4_mutating_github_api_pr_calls_are_denied(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "GitHub branch protection" in denial["reason"]


def test_n5_plain_xargs_without_git_or_gh_is_allowed(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    allowed(run_hook(repo, home, bash_payload("find . -type f | xargs wc -l", repo)))


@pytest.mark.parametrize(
    "rollup,bad_name",
    [
        ([{"__typename": "CheckRun", "name": "ci", "conclusion": None}], "ci"),
        ([{"__typename": "StatusContext", "context": "lint", "state": "FAILURE"}], "lint"),
        ([{"__typename": "StatusContext", "context": "lint", "state": "SUCCESS"}, {"__typename": "CheckRun", "name": "ci", "conclusion": None}], "ci"),
    ],
)
def test_n6_ci_rollup_requires_success_by_type(tmp_path, rollup, bad_name):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    head = git(repo, "rev-parse", "HEAD")
    gh_bin = fake_gh(tmp_path, head=head, rollup=rollup)

    denial = denied(run_hook(repo, home, bash_payload("gh pr ready", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))

    assert bad_name in denial["reason"]


def test_n6_status_context_success_is_allowed(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    head = git(repo, "rev-parse", "HEAD")
    gh_bin = fake_gh(tmp_path, head=head, rollup=[{"__typename": "StatusContext", "context": "lint", "state": "SUCCESS"}])

    allowed(run_hook(repo, home, bash_payload("gh pr ready", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))


def test_n7_base_fallback_uses_master_when_main_is_absent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "master")
    write(repo / "app.py", "VALUE = 1\n")
    commit_all(repo, "base\n")
    git(repo, "checkout", "-qb", "feature")
    write(repo / "app.py", "VALUE = 2\n")
    commit_all(repo, "change\n")
    home = tmp_path / "home"

    allowed(run_hook(repo, home, bash_payload("git push", repo)))


def test_n7_missing_base_reason_names_missing_base(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    git(repo, "branch", "-D", "main")

    denial = denied(run_hook(repo, home, bash_payload("git push", repo)))

    assert "missing base" in denial["reason"]


@pytest.mark.parametrize("command", ["(( git push --all ))", "{ git push --mirror; }", "( git push --tags )", "git push --follow-tags"])
def test_b1_b3_grouped_and_tag_push_modes_are_denied(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "ambiguous" in denial["reason"]


@pytest.mark.parametrize("command", ["git commit --allow-empty -m x && ( git push )", "{ git merge main; } && gh pr ready"])
def test_b1_grouped_mutation_before_publication_is_denied(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "as its own tool call" in denial["reason"]


@pytest.mark.parametrize("command", ["$GIT push", "`which git` push", "TOOL=$GIT $TOOL push", "cmd=$GH $cmd pr ready"])
def test_b2_variable_executable_with_publication_words_is_denied(tmp_path, command):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    denial = denied(run_hook(repo, home, bash_payload(command, repo)))

    assert "unreadable command head" in denial["reason"]


def test_b2_variable_executable_without_publication_words_is_allowed(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"

    allowed(run_hook(repo, home, bash_payload("$TOOL status", repo)))


def test_h1_pr_number_requires_head_to_exist_locally(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    remote_head = "b" * 40
    gh_bin = fake_gh(
        tmp_path,
        head=remote_head,
        rollup=[{"__typename": "CheckRun", "name": "ci", "conclusion": "SUCCESS"}],
        extra={"url": "https://github.com/owner/repo/pull/123", "headRepository": {"nameWithOwner": "owner/repo"}},
    )
    git(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")

    denial = denied(run_hook(repo, home, bash_payload("gh pr ready --repo owner/repo 123", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))

    assert "PR is not from this repo" in denial["reason"]


def test_h1_pr_number_requires_base_repo_to_match_local_remote(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    head = git(repo, "rev-parse", "HEAD")
    gh_bin = fake_gh(
        tmp_path,
        head=head,
        rollup=[{"__typename": "CheckRun", "name": "ci", "conclusion": "SUCCESS"}],
        extra={"url": "https://github.com/other/repo/pull/123", "headRepository": {"nameWithOwner": "other/repo"}},
    )
    git(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")

    denial = denied(run_hook(repo, home, bash_payload("gh pr ready --repo other/repo 123", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))

    assert "PR is not from this repo" in denial["reason"]


def test_h2_gh_global_repo_option_is_guarded_and_reaches_ci(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    head = git(repo, "rev-parse", "HEAD")
    gh_bin = fake_gh(
        tmp_path,
        head=head,
        rollup=[{"__typename": "CheckRun", "name": "ci", "conclusion": "SUCCESS"}],
        extra={"url": "https://github.com/owner/repo/pull/123", "headRepository": {"nameWithOwner": "owner/repo"}},
    )
    git(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")

    allowed(run_hook(repo, home, bash_payload("gh --repo owner/repo pr ready 123", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))


def test_h2_github_pr_url_carries_repo_identity(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    head = git(repo, "rev-parse", "HEAD")
    gh_bin = fake_gh(
        tmp_path,
        head=head,
        rollup=[{"__typename": "CheckRun", "name": "ci", "conclusion": "SUCCESS"}],
        extra={"url": "https://github.com/owner/repo/pull/123", "headRepository": {"nameWithOwner": "owner/repo"}},
    )
    git(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")

    allowed(run_hook(repo, home, bash_payload("gh pr ready https://github.com/owner/repo/pull/123", repo), extra_env={"PATH": f"{gh_bin}:{os.environ['PATH']}"}))



@pytest.mark.skipif(shutil.which("gh") is None, reason="gh is not installed")
def test_gate_asks_gh_pr_view_only_for_fields_the_installed_gh_accepts():
    # An unknown --json field makes gh exit non-zero, which failed every real `gh pr ready` closed.
    listing = subprocess.run(["gh", "pr", "view", "1", "--repo", "o/r", "--json", "__none__"],
                             capture_output=True, text=True, timeout=30, env={**os.environ, "GH_HOST": "github.com"})
    available = {line.strip() for line in listing.stderr.splitlines() if line.startswith("  ")}
    assert available, listing.stderr
    source = SHIP_GATE.read_text()
    fields = re.search(r"GH_PR_FIELDS = \(([^)]*)\)", source).group(1)
    assert set(re.findall(r'"([A-Za-z]+)"', fields)) <= available
