import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect

from keel.db.engine import create_db_engine
from keel.db.revision import alembic_config, current_revision, head_revision
from keel.db.worktree import (
    WORKTREE_DATABASE,
    WorktreeDatabaseChoice,
    choose_worktree_database,
    database_url_is_set,
    describe_choice,
    prepare_worktree_database,
    read_stamped_revision,
    revisions_that_reach_head,
    with_database_url,
)


def _stamp(path: Path, revision: str) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
    )
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES (?)",
        (revision,),
    )
    connection.commit()
    connection.close()


def test_a_commented_database_url_is_unset() -> None:
    text = "# KEEL_DATABASE_URL=sqlite+pysqlite:///C:/shared/keel.db\n"
    assert database_url_is_set(text) is False
    updated = with_database_url(text, "sqlite+pysqlite:///A:/work/.local/keel.db")
    assert database_url_is_set(updated) is True
    assert "KEEL_DATABASE_URL=sqlite+pysqlite:///A:/work/.local/keel.db" in updated
    assert with_database_url(updated, "sqlite+pysqlite:///other.db") == updated


def test_this_checkout_can_upgrade_from_its_own_revisions_only() -> None:
    reachable = revisions_that_reach_head()
    head = head_revision(alembic_config("sqlite://"))
    assert head is not None
    assert head in reachable
    assert "0001" in reachable
    assert "9999" not in reachable


def test_the_main_checkout_keeps_the_shared_database(tmp_path: Path) -> None:
    shared = tmp_path / "shared.db"
    _stamp(shared, "0028")
    before = shared.read_bytes()
    repo = tmp_path / "main"
    repo.mkdir()
    code = prepare_worktree_database(
        repo,
        force_empty=True,
        linked=False,
        shared_database=shared,
    )
    assert code == 0
    assert shared.read_bytes() == before
    assert not (repo / ".env").exists()
    assert not (repo / WORKTREE_DATABASE).exists()


def test_an_unknown_revision_starts_an_empty_worktree_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = tmp_path / "shared.db"
    _stamp(shared, "9999")
    before = shared.read_bytes()
    repo = tmp_path / "worktree"
    repo.mkdir()
    code = prepare_worktree_database(repo, linked=True, shared_database=shared)
    assert code == 0
    assert shared.read_bytes() == before
    assert read_stamped_revision(shared) == "9999"
    destination = repo / WORKTREE_DATABASE
    url = f"sqlite+pysqlite:///{destination.resolve().as_posix()}"
    assert url in (repo / ".env").read_text(encoding="utf-8")
    engine = create_db_engine(url)
    try:
        assert current_revision(engine) == head_revision(alembic_config(url))
    finally:
        engine.dispose()
    message = capsys.readouterr().out
    assert "9999" in message
    assert "empty database" in message


def test_a_known_revision_is_copied_and_the_shared_file_stays_put(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = tmp_path / "shared.db"
    head = head_revision(alembic_config("sqlite://"))
    assert head is not None
    _stamp(shared, head)
    before = shared.read_bytes()
    repo = tmp_path / "worktree"
    repo.mkdir()
    code = prepare_worktree_database(repo, linked=True, shared_database=shared)
    assert code == 0
    assert shared.read_bytes() == before
    assert read_stamped_revision(shared) == head
    destination = repo / WORKTREE_DATABASE
    assert read_stamped_revision(destination) == head
    assert "Copied the shared development database" in capsys.readouterr().out


def test_empty_database_flag_skips_a_copyable_shared_file(tmp_path: Path) -> None:
    shared = tmp_path / "shared.db"
    head = head_revision(alembic_config("sqlite://"))
    assert head is not None
    _stamp(shared, head)
    before = shared.read_bytes()
    repo = tmp_path / "worktree"
    repo.mkdir()
    code = prepare_worktree_database(
        repo,
        force_empty=True,
        linked=True,
        shared_database=shared,
    )
    assert code == 0
    assert shared.read_bytes() == before
    destination = repo / WORKTREE_DATABASE
    engine = create_db_engine(f"sqlite+pysqlite:///{destination.resolve().as_posix()}")
    try:
        assert inspect(engine).has_table("users")
    finally:
        engine.dispose()


def test_a_selected_database_is_left_in_place(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = tmp_path / "shared.db"
    _stamp(shared, "0028")
    before = shared.read_bytes()
    repo = tmp_path / "worktree"
    destination = repo / WORKTREE_DATABASE
    destination.parent.mkdir(parents=True)
    destination.write_text("sentinel", encoding="utf-8")
    (repo / ".env").write_text(
        "KEEL_DATABASE_URL=sqlite+pysqlite:///A:/already/chosen.db\n",
        encoding="utf-8",
    )
    code = prepare_worktree_database(
        repo,
        force_empty=True,
        linked=True,
        shared_database=shared,
    )
    assert code == 0
    assert destination.read_text(encoding="utf-8") == "sentinel"
    assert shared.read_bytes() == before
    assert (repo / ".env").read_text(encoding="utf-8") == (
        "KEEL_DATABASE_URL=sqlite+pysqlite:///A:/already/chosen.db\n"
    )
    assert "Leaving it in place" in capsys.readouterr().out


def test_running_setup_again_does_not_replace_the_worktree_database(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared.db"
    head = head_revision(alembic_config("sqlite://"))
    assert head is not None
    _stamp(shared, head)
    repo = tmp_path / "worktree"
    repo.mkdir()
    assert prepare_worktree_database(repo, linked=True, shared_database=shared) == 0
    destination = repo / WORKTREE_DATABASE
    marker = destination.read_bytes()
    shared.write_bytes(b"")
    assert prepare_worktree_database(repo, linked=True, shared_database=shared) == 0
    assert destination.read_bytes() == marker


def test_choice_messages_name_the_reason() -> None:
    assert (
        choose_worktree_database(
            linked=True,
            database_url_set=False,
            force_empty=False,
            shared_exists=False,
            shared_revision=None,
            reachable=set(),
        )
        is WorktreeDatabaseChoice.EMPTY_MISSING
    )
    missing = describe_choice(WorktreeDatabaseChoice.EMPTY_MISSING, None)
    assert missing is not None
    assert "No shared development database" in missing
    forced = describe_choice(WorktreeDatabaseChoice.EMPTY_FORCED, "0027")
    assert forced is not None
    assert "--empty-database" in forced
    unreadable = describe_choice(WorktreeDatabaseChoice.EMPTY_UNKNOWN, None)
    assert unreadable is not None
    assert "no revision" in unreadable


def test_env_assignment_accepts_export_and_rejects_a_blank_value() -> None:
    assert database_url_is_set("export KEEL_DATABASE_URL=sqlite://x\n") is True
    assert database_url_is_set("KEEL_DATABASE_URL=\nKEEL_HOST=127.0.0.1\n") is False
    updated = with_database_url("KEEL_HOST=127.0.0.1", "sqlite://x")
    assert updated.endswith("KEEL_DATABASE_URL=sqlite://x\n")
    assert updated.startswith("KEEL_HOST=127.0.0.1\n")


def test_an_unreadable_database_has_no_revision(tmp_path: Path) -> None:
    junk = tmp_path / "junk.db"
    junk.write_text("not a database", encoding="utf-8")
    assert read_stamped_revision(junk) is None
    empty = tmp_path / "empty.db"
    connection = sqlite3.connect(empty)
    connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES (NULL)")
    connection.commit()
    connection.close()
    assert read_stamped_revision(empty) is None


def test_copy_refuses_to_overwrite_the_source(tmp_path: Path) -> None:
    database = tmp_path / "keel.db"
    _stamp(database, "0027")
    with pytest.raises(OSError, match="onto itself"):
        from keel.db.worktree import copy_database_readonly

        copy_database_readonly(database, database)


def test_sidecars_are_removed_with_the_database(tmp_path: Path) -> None:
    from keel.db.worktree import remove_database

    database = tmp_path / "keel.db"
    database.write_text("db", encoding="utf-8")
    Path(f"{database}-wal").write_text("wal", encoding="utf-8")
    Path(f"{database}-shm").write_text("shm", encoding="utf-8")
    remove_database(database)
    assert not database.exists()
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_git_failure_is_not_a_linked_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel.db.worktree import is_linked_worktree

    def fail(*_args: object, **_kwargs: object) -> str:
        raise OSError("git missing")

    monkeypatch.setattr("keel.db.worktree.subprocess.check_output", fail)
    assert is_linked_worktree(tmp_path) is False


def test_prepare_detects_a_main_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("keel.db.worktree.is_linked_worktree", lambda _root: False)
    shared = tmp_path / "shared.db"
    _stamp(shared, "0028")
    repo = tmp_path / "main"
    repo.mkdir()
    assert prepare_worktree_database(repo, shared_database=shared) == 0
    assert not (repo / ".env").exists()


def test_prepare_refuses_to_use_the_shared_file_as_the_worktree_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    head = head_revision(alembic_config("sqlite://"))
    assert head is not None
    repo = tmp_path / "worktree"
    shared = repo / WORKTREE_DATABASE
    shared.parent.mkdir(parents=True)
    _stamp(shared, head)
    before = shared.read_bytes()
    code = prepare_worktree_database(repo, linked=True, shared_database=shared)
    assert code == 1
    assert shared.read_bytes() == before
    assert "onto itself" in capsys.readouterr().err


def test_a_failed_upgrade_removes_the_new_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from alembic.util.exc import CommandError

    def fail(_config: object) -> None:
        raise CommandError("upgrade failed")

    monkeypatch.setattr("keel.db.worktree.upgrade_to_head", fail)
    repo = tmp_path / "worktree"
    repo.mkdir()
    shared = tmp_path / "missing.db"
    code = prepare_worktree_database(repo, linked=True, shared_database=shared)
    assert code == 1
    assert not (repo / WORKTREE_DATABASE).exists()
    assert not (repo / ".env").exists()
    assert "upgrade failed" in capsys.readouterr().err


def test_relative_git_directories_mark_a_linked_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel.db.worktree import is_linked_worktree

    answers = {
        "--git-dir": ".git/worktrees/KEEL-127\n",
        "--git-common-dir": ".git\n",
    }

    def output(args: list[str], **_kwargs: object) -> str:
        return answers[args[-1]]

    monkeypatch.setattr("keel.db.worktree.subprocess.check_output", output)
    assert is_linked_worktree(tmp_path) is True
    answers["--git-dir"] = f"{(tmp_path / '.git').resolve()}\n"
    answers["--git-common-dir"] = f"{(tmp_path / '.git').resolve()}\n"
    assert is_linked_worktree(tmp_path) is False


def test_cli_prepares_the_current_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel import cli

    seen: dict[str, object] = {}

    def fake(root: Path, *, force_empty: bool = False) -> int:
        seen["root"] = root
        seen["empty"] = force_empty
        return 0

    monkeypatch.setattr(cli, "prepare_worktree_database", fake)
    assert cli.main(["db", "prepare-worktree", "--empty-database"]) == 0
    assert seen["empty"] is True
    assert seen["root"] == Path.cwd()
