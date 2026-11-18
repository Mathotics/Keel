import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("prune-worktrees.ps1", "prune-worktrees.sh", "prune-worktrees.bat")


def _bash_executable() -> str | None:
    git = shutil.which("git")
    if git is not None:
        candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("bash")
    if found is None:
        return None
    if Path(found).match("System32/bash.exe"):
        return None
    return found


def _runners() -> list[str]:
    found: list[str] = []
    if os.name == "nt" and shutil.which("powershell"):
        found.append("powershell")
    if os.name == "nt" and shutil.which("cmd"):
        found.append("bat")
    if _bash_executable() is not None:
        found.append("bash")
    return found


RUNNERS = _runners()


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    # Pre-commit exports GIT_DIR and the index. A temp repo must not inherit them.
    merged = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "PRE_COMMIT"))
    }
    merged["GIT_AUTHOR_NAME"] = "Test"
    merged["GIT_AUTHOR_EMAIL"] = "test@example.com"
    merged["GIT_COMMITTER_NAME"] = "Test"
    merged["GIT_COMMITTER_EMAIL"] = "test@example.com"
    merged["PRE_COMMIT_ALLOW_NO_CONFIG"] = "1"
    if extra is not None:
        merged.update(extra)
    return merged


def _git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(env),
    )
    if completed.returncode != 0:
        message = completed.stdout + completed.stderr
        raise AssertionError(message)


def _run(
    runner: str,
    repo: Path,
    *args: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    script = (
        repo
        / "scripts"
        / {
            "powershell": "prune-worktrees.ps1",
            "bat": "prune-worktrees.bat",
            "bash": "prune-worktrees.sh",
        }[runner]
    )
    if runner == "powershell":
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ]
    elif runner == "bat":
        command = ["cmd", "/c", str(script), *args]
    else:
        bash = _bash_executable()
        assert bash is not None
        command = [bash, str(script), *args]
    return subprocess.run(
        command,
        cwd=cwd or repo,
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )


def _output(completed: subprocess.CompletedProcess[str]) -> str:
    return completed.stdout + completed.stderr


def _build(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    parent = Path(str(repo) + ".worktrees")
    parent.mkdir()
    _git(repo, "worktree", "add", "-b", "merged-wt", str(parent / "merged-wt"))
    _git(repo, "worktree", "add", "-b", "fresh-wt", str(parent / "fresh-wt"))
    _git(parent / "fresh-wt", "commit", "--allow-empty", "-m", "fresh")
    _git(repo, "worktree", "add", "-b", "old-wt", str(parent / "old-wt"))
    old = {
        "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z",
    }
    _git(parent / "old-wt", "commit", "--allow-empty", "-m", "old", env=old)
    _git(repo, "worktree", "add", "-b", "dirty-wt", str(parent / "dirty-wt"))
    (parent / "dirty-wt" / "notes.txt").write_text("dirty\n", encoding="utf-8")
    _git(repo, "branch", "merged-loose")
    _git(repo, "checkout", "-b", "fresh-loose")
    _git(repo, "commit", "--allow-empty", "-m", "loose")
    _git(repo, "checkout", "main")
    destination = repo / "scripts"
    destination.mkdir()
    for name in SCRIPTS:
        shutil.copyfile(ROOT / "scripts" / name, destination / name)
    return repo


def _exists(repo: Path, name: str) -> bool:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{name}",
        ],
        check=False,
        capture_output=True,
        env=_git_env(),
    )
    return completed.returncode == 0


def _worktree_exists(repo: Path, name: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    marker = f".worktrees/{name}"
    marker_windows = f".worktrees\\{name}"
    text = completed.stdout
    return marker in text or marker_windows in text


@pytest.mark.skipif(not RUNNERS, reason="no shell can run prune-worktrees")
@pytest.mark.parametrize("runner", RUNNERS)
def test_help_and_rejected_arguments(runner: str, tmp_path: Path) -> None:
    repo = _build(tmp_path)
    help_run = _run(runner, repo, "--help")
    assert help_run.returncode == 0, _output(help_run)
    assert "--dry-run" in help_run.stdout
    assert "--stale" in help_run.stdout
    unknown = _run(runner, repo, "--nope")
    assert unknown.returncode == 1, _output(unknown)
    skipped = _run(runner, repo, "--skip-merged")
    assert skipped.returncode == 1, _output(skipped)


@pytest.mark.skipif(not RUNNERS, reason="no shell can run prune-worktrees")
@pytest.mark.parametrize("runner", RUNNERS)
def test_default_removes_merged_pairs_and_keeps_the_rest(
    runner: str, tmp_path: Path
) -> None:
    repo = _build(tmp_path)
    dry = _run(runner, repo, "--dry-run")
    text = _output(dry)
    assert dry.returncode == 0, text
    assert "remove worktree" in text
    assert "merged-wt" in text
    assert "delete branch merged-loose" in text
    assert "dirty-wt" in text
    assert "uncommitted changes" in text
    assert "fresh-wt" not in text
    assert "fresh-loose" not in text
    assert "old-wt" not in text
    assert "delete branch main" not in text
    assert _worktree_exists(repo, "merged-wt")

    done = _run(runner, repo)
    assert done.returncode == 0, _output(done)
    assert not _worktree_exists(repo, "merged-wt")
    assert not _exists(repo, "merged-wt")
    assert not _exists(repo, "merged-loose")
    assert _worktree_exists(repo, "fresh-wt")
    assert _worktree_exists(repo, "old-wt")
    assert _worktree_exists(repo, "dirty-wt")
    assert _exists(repo, "fresh-loose")
    assert _exists(repo, "main")


@pytest.mark.skipif(not RUNNERS, reason="no shell can run prune-worktrees")
@pytest.mark.parametrize("runner", RUNNERS)
def test_force_discards_a_dirty_merged_worktree(runner: str, tmp_path: Path) -> None:
    repo = _build(tmp_path)
    done = _run(runner, repo, "--force")
    assert done.returncode == 0, _output(done)
    assert not _worktree_exists(repo, "dirty-wt")
    assert not _exists(repo, "dirty-wt")
    assert _worktree_exists(repo, "fresh-wt")
    assert _worktree_exists(repo, "old-wt")


@pytest.mark.skipif(not RUNNERS, reason="no shell can run prune-worktrees")
@pytest.mark.parametrize("runner", RUNNERS)
def test_stale_unmerged_work_needs_force(runner: str, tmp_path: Path) -> None:
    repo = _build(tmp_path)
    skipped = _run(runner, repo, "--skip-merged", "--stale")
    text = _output(skipped)
    assert skipped.returncode == 0, text
    assert "old-wt" in text
    assert "not merged" in text
    assert _worktree_exists(repo, "old-wt")
    assert _worktree_exists(repo, "merged-wt")

    done = _run(runner, repo, "--skip-merged", "--stale", "--force")
    assert done.returncode == 0, _output(done)
    assert not _worktree_exists(repo, "old-wt")
    assert not _exists(repo, "old-wt")
    assert _worktree_exists(repo, "merged-wt")
    assert _worktree_exists(repo, "fresh-wt")


@pytest.mark.skipif(not RUNNERS, reason="no shell can run prune-worktrees")
@pytest.mark.parametrize("runner", RUNNERS)
def test_worktrees_only_leaves_loose_branches(runner: str, tmp_path: Path) -> None:
    repo = _build(tmp_path)
    dry = _run(runner, repo, "--worktrees-only", "--dry-run")
    text = _output(dry)
    assert dry.returncode == 0, text
    assert "merged-wt" in text
    assert "delete branch merged-loose" not in text


@pytest.mark.skipif(not RUNNERS, reason="no shell can run prune-worktrees")
@pytest.mark.parametrize("runner", RUNNERS)
def test_the_worktree_you_started_from_is_kept(runner: str, tmp_path: Path) -> None:
    repo = _build(tmp_path)
    started = Path(str(repo) + ".worktrees") / "merged-wt"
    done = _run(runner, repo, cwd=started)
    assert done.returncode == 0, _output(done)
    assert _worktree_exists(repo, "merged-wt")
    assert _exists(repo, "merged-wt")
    assert not _exists(repo, "merged-loose")


def test_onboard_registers_the_prune_alias() -> None:
    for name in ("onboard.ps1", "onboard.sh", "onboard.bat"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "prune-worktrees" in text
        assert "scripts/prune-worktrees.sh" in text
