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


def resolve(cwd: Path, docs_home: Path, *args: str) -> Path:
    env = os.environ.copy()
    env["CE_DOCS_HOME"] = str(docs_home)
    result = subprocess.run(
        [str(RESOLVER), "--cwd", str(cwd), *args],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.stdout.endswith("\n")
    assert len(result.stdout.splitlines()) == 1
    return Path(result.stdout.strip())


def set_origin(repo: Path, url: str) -> None:
    run("git", "remote", "add", "origin", url, cwd=repo)


def test_plain_repo_maps_to_docs_basename(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    docs_home = tmp_path / "docs"

    result = resolve(repo, docs_home)

    assert result == docs_home / "alpha"
    assert (result / ".ce-repository-identity").read_text().endswith("\n")


def test_linked_worktree_maps_to_same_root_as_main_checkout(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    run("git", "config", "user.email", "test@example.com", cwd=repo)
    run("git", "config", "user.name", "Test User", cwd=repo)
    (repo / "tracked.txt").write_text("content\n")
    run("git", "add", "tracked.txt", cwd=repo)
    run("git", "commit", "-q", "-m", "initial", cwd=repo)
    worktree = tmp_path / "alpha-worktree"
    run("git", "worktree", "add", "-q", "--detach", str(worktree), cwd=repo)
    docs_home = tmp_path / "docs"

    assert resolve(repo, docs_home) == resolve(worktree, docs_home)


def test_origin_url_defines_identity_independent_of_checkout_path(tmp_path):
    first = init_repo(tmp_path / "first-checkout")
    second = init_repo(tmp_path / "second-checkout")
    origin = "https://example.com/acme/shared.git/"
    set_origin(first, origin)
    set_origin(second, origin)
    docs_home = tmp_path / "docs"

    assert resolve(first, docs_home) == resolve(second, docs_home) == docs_home / "shared"


def test_name_collision_gets_stable_eight_character_hash_suffix(tmp_path):
    repo = init_repo(tmp_path / "checkout")
    set_origin(repo, "https://user:secret@example.com/acme/alpha.git")
    docs_home = tmp_path / "docs"
    occupied = docs_home / "alpha"
    occupied.mkdir(parents=True)
    (occupied / ".ce-repository-identity").write_text("another identity\n")
    identity = "https://example.com/acme/alpha"
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:8]

    result = resolve(repo, docs_home)

    assert result == docs_home / f"alpha-{suffix}"
    assert (result / ".ce-repository-identity").read_text() == f"{identity}\n"


def test_existing_matching_marker_reuses_directory(tmp_path):
    repo = init_repo(tmp_path / "checkout")
    set_origin(repo, "ssh://git@example.com/acme/alpha.git")
    docs_home = tmp_path / "docs"
    existing = docs_home / "alpha"
    existing.mkdir(parents=True)
    identity = "ssh://example.com/acme/alpha"
    (existing / ".ce-repository-identity").write_text(f"{identity}\n")

    assert resolve(repo, docs_home) == existing


def test_no_create_prints_path_without_writing(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    docs_home = tmp_path / "docs"

    assert resolve(repo, docs_home, "--no-create") == docs_home / "alpha"
    assert not docs_home.exists()


def test_non_repo_maps_to_docs_general(tmp_path):
    plain_directory = tmp_path / "not-a-repository"
    plain_directory.mkdir()
    docs_home = tmp_path / "docs"

    assert resolve(plain_directory, docs_home) == docs_home / "general"


def test_repository_directory_symlink_outside_docs_is_refused_before_writing(tmp_path):
    repo = init_repo(tmp_path / "alpha")
    docs_home = tmp_path / "docs"
    docs_home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (docs_home / "alpha").symlink_to(outside, target_is_directory=True)
    env = os.environ.copy()
    env["CE_DOCS_HOME"] = str(docs_home)

    result = subprocess.run(
        [str(RESOLVER), "--cwd", str(repo)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode != 0
    assert not (outside / ".ce-repository-identity").exists()
