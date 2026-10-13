import hashlib
import importlib.util
import os
import subprocess
import threading
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


RESOLVER = Path(__file__).resolve().parents[1] / "bin" / "ce-artifact-root"


def load_resolver_module():
    loader = SourceFileLoader("ce_artifact_root", str(RESOLVER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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


@pytest.mark.parametrize(
    "variant",
    [
        "https://example.com/acme/shared.git/?ref=main",
        "https://example.com/acme/shared.git/#readme",
    ],
)
def test_origin_url_query_and_fragment_do_not_change_identity(tmp_path, variant):
    canonical = init_repo(tmp_path / "canonical-checkout")
    equivalent = init_repo(tmp_path / "equivalent-checkout")
    set_origin(canonical, "https://example.com/acme/shared")
    set_origin(equivalent, variant)
    home = make_home(tmp_path)

    assert resolve(canonical, home) == resolve(equivalent, home) == home / "docs" / "shared"


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


def test_interrupted_marker_publication_leaves_no_marker_or_temporary_file(
    tmp_path, monkeypatch
):
    resolver = load_resolver_module()
    repo = init_repo(tmp_path / "alpha")
    docs_home = tmp_path / "docs"

    def interrupt_fsync(descriptor):
        raise OSError("simulated interruption")

    monkeypatch.setattr(resolver.os, "fsync", interrupt_fsync)

    with pytest.raises(OSError, match="simulated interruption"):
        resolver.resolve_artifact_root(repo, docs_home, True)

    artifact_root = docs_home / "alpha"
    assert not (artifact_root / ".ce-repository-identity").exists()
    assert list(artifact_root.iterdir()) == []


def test_concurrent_resolvers_only_observe_complete_marker_publications(
    tmp_path, monkeypatch
):
    resolver = load_resolver_module()
    first = init_repo(tmp_path / "first-checkout")
    second = init_repo(tmp_path / "second-checkout")
    origin = "https://example.com/acme/alpha.git"
    set_origin(first, origin)
    set_origin(second, origin)
    docs_home = tmp_path / "docs"
    write_started = threading.Event()
    release_write = threading.Event()
    real_fdopen = resolver.os.fdopen
    writer_count = 0
    count_lock = threading.Lock()

    class DelayedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, content):
            write_started.set()
            assert release_write.wait(timeout=5)
            return self.stream.write(content)

    def delay_first_writer(*args, **kwargs):
        nonlocal writer_count
        stream = real_fdopen(*args, **kwargs)
        if len(args) > 1 and args[1] == "w":
            with count_lock:
                writer_count += 1
                if writer_count == 1:
                    return DelayedWriter(stream)
        return stream

    monkeypatch.setattr(resolver.os, "fdopen", delay_first_writer)
    roots = {}
    errors = []

    def resolve_repository(label, repo):
        try:
            roots[label] = resolver.resolve_artifact_root(repo, docs_home, True)
        except Exception as error:
            errors.append(error)

    first_thread = threading.Thread(
        target=resolve_repository, args=("first", first)
    )
    first_thread.start()
    assert write_started.wait(timeout=5)
    second_thread = threading.Thread(
        target=resolve_repository, args=("second", second)
    )
    second_thread.start()
    second_thread.join(timeout=5)
    second_completed_before_publication = not second_thread.is_alive()
    release_write.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert second_completed_before_publication
    assert not first_thread.is_alive()
    assert errors == []
    assert roots == {
        "first": docs_home / "alpha",
        "second": docs_home / "alpha",
    }
    marker = docs_home / "alpha" / ".ce-repository-identity"
    assert marker.read_text() == "https://example.com/acme/alpha\n"
    assert [path.name for path in marker.parent.iterdir()] == [marker.name]
