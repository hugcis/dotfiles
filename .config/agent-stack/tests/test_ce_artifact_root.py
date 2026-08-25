import hashlib
import os
import subprocess
from pathlib import Path


RESOLVER = Path(__file__).resolve().parents[1] / "bin" / "ce-artifact-root"


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def init_repo(path: Path) -> Path:
    path.mkdir()
    run("git", "init", "-q", str(path))
    return path


def make_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def invoke(cwd: Path, home: Path, *args: str, **env_overrides: str):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("CE_DOCS_HOME", None)
    env.update(env_overrides)
    return subprocess.run(
        [str(RESOLVER), "--cwd", str(cwd), *args],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def resolve(cwd: Path, home: Path, *args: str, **env_overrides: str) -> Path:
    result = invoke(cwd, home, *args, **env_overrides)
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("\n")
    assert len(result.stdout.splitlines()) == 1
    return Path(result.stdout.strip())


def set_origin(repo: Path, url: str) -> None:
    run("git", "remote", "add", "origin", url, cwd=repo)


def test_plain_repo_maps_to_docs_basename(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    home = make_home(tmp_path)

    result = resolve(repo, home)

    assert result == home / "docs" / "alpha"
    assert (result / ".ce-repository-identity").read_text().endswith("\n")


def test_docs_home_environment_override_is_ignored(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    home = make_home(tmp_path)
    decoy = tmp_path / "decoy-docs"

    result = resolve(repo, home, CE_DOCS_HOME=str(decoy))

    assert result == home / "docs" / "alpha"
    assert not decoy.exists()


def test_linked_worktree_maps_to_same_root_as_main_checkout(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    run("git", "config", "user.email", "test@example.com", cwd=repo)
    run("git", "config", "user.name", "Test User", cwd=repo)
    (repo / "tracked.txt").write_text("content\n")
    run("git", "add", "tracked.txt", cwd=repo)
    run("git", "commit", "-q", "-m", "initial", cwd=repo)
    worktree = tmp_path / "alpha-worktree"
    run("git", "worktree", "add", "-q", "--detach", str(worktree), cwd=repo)
    home = make_home(tmp_path)

    assert resolve(repo, home) == resolve(worktree, home)


def test_separate_git_dir_linked_worktree_shares_root_with_main_checkout(tmp_path):
    repo = tmp_path / "alpha"
    repo.mkdir()
    git_dir = tmp_path / "gitdirs" / "alpha.git"
    git_dir.parent.mkdir()
    run("git", "init", "-q", f"--separate-git-dir={git_dir}", str(repo))
    run("git", "config", "user.email", "test@example.com", cwd=repo)
    run("git", "config", "user.name", "Test User", cwd=repo)
    run("git", "commit", "-q", "--allow-empty", "-m", "initial", cwd=repo)
    worktree = tmp_path / "alpha-worktree"
    run("git", "worktree", "add", "-q", "--detach", str(worktree), cwd=repo)
    home = make_home(tmp_path)

    main_root = resolve(repo, home)

    assert main_root == home / "docs" / "alpha"
    assert resolve(worktree, home) == main_root


def test_origin_url_defines_identity_independent_of_checkout_path(tmp_path):
    first = init_repo(tmp_path / "first-checkout")
    second = init_repo(tmp_path / "second-checkout")
    origin = "https://example.com/acme/shared.git/"
    set_origin(first, origin)
    set_origin(second, origin)
    home = make_home(tmp_path)
    docs_home = home / "docs"

    assert resolve(first, home) == resolve(second, home) == docs_home / "shared"


def test_name_collision_gets_stable_eight_character_hash_suffix(tmp_path):
    repo = init_repo(tmp_path / "checkout")
    set_origin(repo, "https://user:secret@example.com/acme/alpha.git")
    home = make_home(tmp_path)
    docs_home = home / "docs"
    occupied = docs_home / "alpha"
    occupied.mkdir(parents=True)
    (occupied / ".ce-repository-identity").write_text("another identity\n")
    identity = "https://example.com/acme/alpha"
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:8]

    result = resolve(repo, home)

    assert result == docs_home / f"alpha-{suffix}"
    assert (result / ".ce-repository-identity").read_text() == f"{identity}\n"


def test_existing_matching_marker_reuses_directory(tmp_path):
    repo = init_repo(tmp_path / "checkout")
    set_origin(repo, "ssh://git@example.com/acme/alpha.git")
    home = make_home(tmp_path)
    existing = home / "docs" / "alpha"
    existing.mkdir(parents=True)
    identity = "ssh://example.com/acme/alpha"
    (existing / ".ce-repository-identity").write_text(f"{identity}\n")

    assert resolve(repo, home) == existing


def test_no_create_prints_path_without_writing(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    home = make_home(tmp_path)

    assert resolve(repo, home, "--no-create") == home / "docs" / "alpha"
    assert not (home / "docs").exists()


def test_non_repo_maps_to_docs_general(tmp_path):
    plain_directory = tmp_path / "not-a-repository"
    plain_directory.mkdir()
    home = make_home(tmp_path)

    assert resolve(plain_directory, home) == home / "docs" / "general"


def test_repository_directory_symlink_outside_docs_is_refused_before_writing(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    home = make_home(tmp_path)
    docs_home = home / "docs"
    docs_home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (docs_home / "alpha").symlink_to(outside, target_is_directory=True)

    result = invoke(repo, home)

    assert result.returncode != 0
    assert not (outside / ".ce-repository-identity").exists()


def test_repository_directory_symlink_inside_docs_is_refused_before_writing(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    home = make_home(tmp_path)
    docs_home = home / "docs"
    target = docs_home / "beta"
    target.mkdir(parents=True)
    (docs_home / "alpha").symlink_to(target, target_is_directory=True)

    result = invoke(repo, home)

    assert result.returncode != 0
    assert not (target / ".ce-repository-identity").exists()


def test_identity_marker_replaced_by_symlink_is_refused_before_writing(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    home = make_home(tmp_path)
    artifact_root = home / "docs" / "alpha"
    artifact_root.mkdir(parents=True)
    planted = tmp_path / "planted.txt"
    planted.write_text("original\n")
    (artifact_root / ".ce-repository-identity").symlink_to(planted)

    result = invoke(repo, home)

    assert result.returncode != 0
    assert planted.read_text() == "original\n"
