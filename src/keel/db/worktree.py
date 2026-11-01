"""A private database for one git worktree.

The main checkout and production keep whatever database they already use.
A linked worktree points KEEL_DATABASE_URL at a file inside that worktree.
"""

import sqlite3
import subprocess
import sys
from enum import Enum
from pathlib import Path

from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError

from keel.db.engine import ensure_database_directory
from keel.db.revision import alembic_config, upgrade_to_head
from keel.paths import database_path

WORKTREE_DATABASE = Path(".local") / "keel.db"
_DATABASE_KEY = "KEEL_DATABASE_URL"


class WorktreeDatabaseChoice(Enum):
    UNCHANGED = "unchanged"
    KEEP = "keep"
    COPY = "copy"
    EMPTY_MISSING = "empty_missing"
    EMPTY_UNKNOWN = "empty_unknown"
    EMPTY_FORCED = "empty_forced"


def revisions_that_reach_head() -> set[str]:
    """Revision ids this checkout can upgrade from, including its head."""
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    head = script.get_current_head()
    if head is None:
        return set()
    return {revision.revision for revision in script.iterate_revisions(head, "base")}


def choose_worktree_database(
    *,
    linked: bool,
    database_url_set: bool,
    force_empty: bool,
    shared_exists: bool,
    shared_revision: str | None,
    reachable: set[str],
) -> WorktreeDatabaseChoice:
    if not linked:
        return WorktreeDatabaseChoice.UNCHANGED
    if database_url_set:
        return WorktreeDatabaseChoice.KEEP
    if force_empty:
        return WorktreeDatabaseChoice.EMPTY_FORCED
    if not shared_exists:
        return WorktreeDatabaseChoice.EMPTY_MISSING
    if shared_revision is not None and shared_revision in reachable:
        return WorktreeDatabaseChoice.COPY
    return WorktreeDatabaseChoice.EMPTY_UNKNOWN


def describe_choice(choice: WorktreeDatabaseChoice, revision: str | None) -> str | None:
    if choice is WorktreeDatabaseChoice.UNCHANGED:
        return None
    if choice is WorktreeDatabaseChoice.KEEP:
        return "This worktree already has a database selected. Leaving it in place."
    if choice is WorktreeDatabaseChoice.COPY:
        return (
            "Copied the shared development database into this worktree and upgraded "
            "the copy. The shared database was not changed."
        )
    if choice is WorktreeDatabaseChoice.EMPTY_MISSING:
        return (
            "No shared development database was found. "
            "Created an empty database for this worktree and upgraded it."
        )
    if choice is WorktreeDatabaseChoice.EMPTY_FORCED:
        return (
            "Created an empty database for this worktree because --empty-database "
            "was set. The shared database was not changed."
        )
    if revision is None:
        detail = (
            "The shared development database has no revision this worktree can upgrade."
        )
    else:
        detail = (
            f"The shared development database is at revision {revision}, "
            "which this worktree cannot upgrade."
        )
    return (
        f"{detail} Created an empty database for this worktree and upgraded it. "
        "The shared database was not changed."
    )


def database_url_is_set(env_text: str) -> bool:
    for raw in env_text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if not stripped.startswith(f"{_DATABASE_KEY}="):
            continue
        value = stripped.split("=", 1)[1].strip().strip("'\"")
        return bool(value)
    return False


def with_database_url(env_text: str, url: str) -> str:
    """Append a database assignment. Leaves an assignment that is already active."""
    if database_url_is_set(env_text):
        return env_text
    body = env_text
    if body and not body.endswith("\n"):
        body += "\n"
    return f"{body}{_DATABASE_KEY}={url}\n"


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve().as_posix()}"


def read_stamped_revision(path: Path) -> str | None:
    """The alembic revision in a database, read without writing to it."""
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def copy_database_readonly(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        raise OSError("Refusing to copy a database onto itself.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    remove_database(destination)
    src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def remove_database(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.is_file():
            candidate.unlink()


def is_linked_worktree(repo_root: Path) -> bool:
    try:
        git_dir = _git_path(repo_root, "--git-dir")
        common = _git_path(repo_root, "--git-common-dir")
    except (OSError, subprocess.CalledProcessError):
        return False
    return git_dir != common


def prepare_worktree_database(
    repo_root: Path,
    *,
    force_empty: bool = False,
    linked: bool | None = None,
    shared_database: Path | None = None,
) -> int:
    """Point a linked worktree at its own database. The shared file is not written."""
    root = repo_root.resolve()
    if linked is None:
        linked = is_linked_worktree(root)
    shared = database_path() if shared_database is None else shared_database
    env_path = root / ".env"
    env_text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    reachable = revisions_that_reach_head()
    shared_exists = shared.is_file()
    revision = read_stamped_revision(shared) if shared_exists else None
    choice = choose_worktree_database(
        linked=linked,
        database_url_set=database_url_is_set(env_text),
        force_empty=force_empty,
        shared_exists=shared_exists,
        shared_revision=revision,
        reachable=reachable,
    )
    message = describe_choice(choice, revision)
    if choice in (WorktreeDatabaseChoice.UNCHANGED, WorktreeDatabaseChoice.KEEP):
        if message is not None:
            print(message)
        return 0

    destination = root / WORKTREE_DATABASE
    if shared_exists and shared.resolve() == destination.resolve():
        print("Refusing to copy a database onto itself.", file=sys.stderr)
        return 1
    url = sqlite_url(destination)
    try:
        if choice is WorktreeDatabaseChoice.COPY:
            copy_database_readonly(shared, destination)
        else:
            remove_database(destination)
        ensure_database_directory(url)
        upgrade_to_head(alembic_config(url))
    except (OSError, sqlite3.Error, CommandError, SQLAlchemyError) as exc:
        remove_database(destination)
        print(str(exc), file=sys.stderr)
        return 1
    env_path.write_text(with_database_url(env_text, url), encoding="utf-8")
    if message is not None:
        print(message)
    return 0


def _git_path(repo_root: Path, flag: str) -> Path:
    output = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", flag],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    path = Path(output.strip())
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()
