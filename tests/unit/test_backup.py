import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from keel.db.backup import (
    BackupError,
    backup_database,
    default_backup_path,
    is_sqlite_file,
    restore_database,
    snapshot,
)


def _url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _live_db(tmp_path: Path) -> tuple[str, Path]:
    live = tmp_path / "keel.db"
    conn = sqlite3.connect(live)
    conn.execute("CREATE TABLE t (n INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    return _url(live), live


def test_default_backup_path_uses_stem_and_local_timestamp(tmp_path: Path) -> None:
    live = tmp_path / "keel.db"
    when = datetime(2026, 9, 2, 14, 30, 0)
    assert default_backup_path(live, when) == tmp_path / "keel-20260902T143000.db"


def test_is_sqlite_file_rejects_junk(tmp_path: Path) -> None:
    junk = tmp_path / "junk.db"
    junk.write_text("not a database", encoding="utf-8")
    assert is_sqlite_file(junk) is False
    assert is_sqlite_file(tmp_path / "missing.db") is False


def test_backup_writes_a_timestamped_sibling(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    when = datetime(2026, 9, 2, 14, 30, 0)
    source, dest = backup_database(url, when=when)
    assert source == live
    assert dest == tmp_path / "keel-20260902T143000.db"
    assert is_sqlite_file(dest)


def test_backup_accepts_a_destination_and_creates_parents(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    dest = tmp_path / "nested" / "copy.db"
    source, written = backup_database(url, dest)
    assert source == live
    assert written == dest
    assert is_sqlite_file(dest)


def test_backup_refuses_a_missing_live_file(tmp_path: Path) -> None:
    live = tmp_path / "keel.db"
    with pytest.raises(BackupError, match="No database at") as excinfo:
        backup_database(_url(live))
    assert str(live) in excinfo.value.message


def test_backup_refuses_an_existing_destination_without_yes(tmp_path: Path) -> None:
    url, _live = _live_db(tmp_path)
    dest = tmp_path / "copy.db"
    backup_database(url, dest)
    with pytest.raises(BackupError, match="already exists") as excinfo:
        backup_database(url, dest)
    assert "--yes" in excinfo.value.message
    backup_database(url, dest, overwrite=True)


def test_backup_refuses_a_non_file_url() -> None:
    with pytest.raises(BackupError, match="only to a SQLite file"):
        backup_database("sqlite://")
    with pytest.raises(BackupError, match="only to a SQLite file"):
        backup_database("postgresql://localhost/keel")


def test_backup_refuses_the_live_file_as_destination(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    with pytest.raises(BackupError, match="live database"):
        backup_database(url, live, overwrite=True)


def test_snapshot_copies_while_the_source_is_open(tmp_path: Path) -> None:
    live = tmp_path / "live.db"
    conn = sqlite3.connect(live)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (n INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    dest = tmp_path / "copy.db"
    snapshot(live, dest)
    conn.execute("INSERT INTO t VALUES (2)")
    conn.commit()
    copied = sqlite3.connect(dest)
    try:
        assert copied.execute("SELECT n FROM t ORDER BY n").fetchall() == [(1,)]
    finally:
        copied.close()
        conn.close()


def test_restore_replaces_the_live_file(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    dest = tmp_path / "copy.db"
    backup_database(url, dest)
    conn = sqlite3.connect(live)
    conn.execute("INSERT INTO t VALUES (99)")
    conn.commit()
    conn.close()
    restore_database(url, dest, overwrite=True)
    conn = sqlite3.connect(live)
    try:
        assert conn.execute("SELECT n FROM t").fetchall() == [(1,)]
    finally:
        conn.close()


def test_restore_without_a_live_file_does_not_need_yes(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    dest = tmp_path / "copy.db"
    backup_database(url, dest)
    live.unlink()
    restore_database(url, dest)
    assert is_sqlite_file(live)


def test_restore_refuses_an_existing_live_file_without_yes(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    dest = tmp_path / "copy.db"
    backup_database(url, dest)
    with pytest.raises(BackupError, match="already exists") as excinfo:
        restore_database(url, dest)
    assert "--yes" in excinfo.value.message
    assert str(live) in excinfo.value.message


def test_restore_refuses_a_missing_source(tmp_path: Path) -> None:
    url, _live = _live_db(tmp_path)
    missing = tmp_path / "missing.db"
    with pytest.raises(BackupError, match="No backup at") as excinfo:
        restore_database(url, missing, overwrite=True)
    assert str(missing) in excinfo.value.message


def test_restore_refuses_a_non_sqlite_source(tmp_path: Path) -> None:
    url, _live = _live_db(tmp_path)
    junk = tmp_path / "junk.db"
    junk.write_text("not a database", encoding="utf-8")
    with pytest.raises(BackupError, match="Not a SQLite database"):
        restore_database(url, junk, overwrite=True)


def test_restore_refuses_a_non_file_url(tmp_path: Path) -> None:
    copy = tmp_path / "copy.db"
    _, live = _live_db(tmp_path)
    backup_database(_url(live), copy)
    with pytest.raises(BackupError, match="only to a SQLite file"):
        restore_database("sqlite://", copy, overwrite=True)


def test_restore_refuses_the_live_file_as_source(tmp_path: Path) -> None:
    url, live = _live_db(tmp_path)
    with pytest.raises(BackupError, match="live database"):
        restore_database(url, live, overwrite=True)
