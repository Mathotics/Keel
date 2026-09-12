"""Copy and restore the live SQLite file without copying WAL sidecars."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from keel.db.engine import BUSY_TIMEOUT_MS, database_file

SQLITE_HEADER = b"SQLite format 3\x00"
BUSY_TIMEOUT_S = BUSY_TIMEOUT_MS / 1000
NOT_A_FILE = "Backup applies only to a SQLite file."


class BackupError(Exception):
    """Refused backup or restore; `message` is printable on stderr."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def default_backup_path(live: Path, when: datetime | None = None) -> Path:
    """Sibling of `live` named `{stem}-{YYYYMMDDTHHMMSS}{suffix}` in local time."""
    stamp = (when or datetime.now()).strftime("%Y%m%dT%H%M%S")
    return live.with_name(f"{live.stem}-{stamp}{live.suffix}")


def is_sqlite_file(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER


def snapshot(source: Path, destination: Path) -> None:
    """Write a consistent copy via SQLite's backup API, even if source is in use."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source, timeout=BUSY_TIMEOUT_S)
    try:
        dest_conn = sqlite3.connect(destination, timeout=BUSY_TIMEOUT_S)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()


def backup_database(
    url: str,
    destination: Path | None = None,
    *,
    overwrite: bool = False,
    when: datetime | None = None,
) -> tuple[Path, Path]:
    live = _live_file(url)
    if not live.is_file():
        raise BackupError(f"No database at {live}.")
    dest = (
        destination.expanduser()
        if destination is not None
        else default_backup_path(live, when)
    )
    if _same_file(live, dest):
        raise BackupError(f"Destination is the live database: {dest}.")
    if dest.exists() and not overwrite:
        raise BackupError(
            f"Destination already exists: {dest}. Pass --yes to overwrite."
        )
    snapshot(live, dest)
    return live, dest


def restore_database(
    url: str, source: Path, *, overwrite: bool = False
) -> tuple[Path, Path]:
    live = _live_file(url)
    source = source.expanduser()
    if not source.is_file():
        raise BackupError(f"No backup at {source}.")
    if not is_sqlite_file(source):
        raise BackupError(f"Not a SQLite database: {source}.")
    if _same_file(source, live):
        raise BackupError(f"Source is the live database: {source}.")
    if live.is_file() and not overwrite:
        raise BackupError(
            f"A database already exists at {live}. Pass --yes to overwrite."
        )
    snapshot(source, live)
    return source, live


def _live_file(url: str) -> Path:
    live = database_file(url)
    if live is None:
        raise BackupError(NOT_A_FILE)
    return live


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False
