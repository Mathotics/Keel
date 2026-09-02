from pathlib import Path

import pytest
from sqlalchemy import inspect

from keel import cli
from keel.db.engine import create_db_engine
from keel.db.revision import (
    alembic_config,
    current_revision,
    head_revision,
    schema_is_current,
)
from keel.settings import KeelSettings


@pytest.fixture
def db_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KeelSettings:
    url = f"sqlite+pysqlite:///{(tmp_path / 'cli.db').as_posix()}"
    settings = KeelSettings(_env_file=None, database_url=url)
    monkeypatch.setattr("keel.cli.get_settings", lambda: settings)
    return settings


def test_alembic_config_carries_the_url_and_scripts() -> None:
    config = alembic_config("sqlite://")
    assert config.get_main_option("sqlalchemy.url") == "sqlite://"
    assert Path(config.get_main_option("script_location") or "").is_dir()


def test_head_revision_is_defined() -> None:
    assert head_revision(alembic_config("sqlite://")) is not None


def test_a_missing_data_directory_reads_as_stale(tmp_path: Path) -> None:
    """The state of a first run: nothing on disk, so serve must say what to run."""
    absent = tmp_path / "not-created-yet" / "keel.db"
    settings = KeelSettings(
        _env_file=None,
        database_url=f"sqlite+pysqlite:///{absent.as_posix()}",
    )
    assert cli.schema_is_stale(settings) is True


def test_an_unusable_database_reads_as_stale(tmp_path: Path) -> None:
    """Whatever the file turns out to be, serve must refuse rather than traceback."""
    junk = tmp_path / "junk.db"
    junk.write_text("this is not a database", encoding="utf-8")
    settings = KeelSettings(
        _env_file=None,
        database_url=f"sqlite+pysqlite:///{junk.as_posix()}",
    )
    assert cli.schema_is_stale(settings) is True


def test_an_unmigrated_database_has_no_revision(db_settings: KeelSettings) -> None:
    engine = create_db_engine(db_settings.resolved_database_url())
    try:
        assert current_revision(engine) is None
    finally:
        engine.dispose()


def test_upgrade_brings_the_schema_to_head(db_settings: KeelSettings) -> None:
    assert cli.schema_is_stale(db_settings) is True
    assert cli.db_upgrade() == 0
    assert cli.schema_is_stale(db_settings) is False

    url = db_settings.resolved_database_url()
    engine = create_db_engine(url)
    try:
        assert inspect(engine).has_table("users")
        assert schema_is_current(engine, alembic_config(url))
        assert current_revision(engine) == head_revision(alembic_config(url))
    finally:
        engine.dispose()


def test_main_routes_db_upgrade(db_settings: KeelSettings) -> None:
    assert cli.main(["db", "upgrade"]) == 0
    assert cli.schema_is_stale(db_settings) is False


def test_db_revision_writes_a_migration_file(db_settings: KeelSettings) -> None:
    cli.db_upgrade()
    scripts = alembic_config("sqlite://").get_main_option("script_location") or ""
    versions = Path(scripts) / "versions"
    before = set(versions.glob("*.py"))
    assert cli.main(["db", "revision", "-m", "temporary check"]) == 0
    created = set(versions.glob("*.py")) - before
    try:
        assert len(created) == 1
    finally:
        for path in created:
            path.unlink()


def test_db_without_a_subcommand_errors() -> None:
    with pytest.raises(SystemExit):
        cli.main(["db"])


def test_db_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["db", "--help"])
    assert excinfo.value.code == 0


def test_backup_copies_the_live_file_and_prints_paths(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.db_upgrade()
    dest = tmp_path / "copy.db"
    assert cli.main(["db", "backup", str(dest)]) == 0
    out = capsys.readouterr().out
    live = tmp_path / "cli.db"
    assert str(live) in out
    assert str(dest) in out
    assert dest.is_file()


def test_backup_default_is_a_timestamped_sibling(
    db_settings: KeelSettings,
    tmp_path: Path,
) -> None:
    cli.db_upgrade()
    assert cli.main(["db", "backup"]) == 0
    copies = list(tmp_path.glob("cli-*.db"))
    assert len(copies) == 1
    assert copies[0].name.startswith("cli-")


def test_backup_refuses_when_the_live_file_is_missing(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["db", "backup"]) == 1
    err = capsys.readouterr().err
    assert "No database at" in err
    assert str(tmp_path / "cli.db") in err


def test_backup_refuses_an_existing_destination_without_yes(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.db_upgrade()
    dest = tmp_path / "copy.db"
    assert cli.main(["db", "backup", str(dest)]) == 0
    capsys.readouterr()
    assert cli.main(["db", "backup", str(dest)]) == 1
    assert "--yes" in capsys.readouterr().err
    assert cli.main(["db", "backup", "-y", str(dest)]) == 0


def test_backup_refuses_a_non_file_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = KeelSettings(_env_file=None, database_url="sqlite://")
    monkeypatch.setattr("keel.cli.get_settings", lambda: settings)
    assert cli.main(["db", "backup"]) == 1
    assert "only to a SQLite file" in capsys.readouterr().err


def test_restore_puts_the_copy_back(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.db_upgrade()
    dest = tmp_path / "copy.db"
    assert cli.main(["db", "backup", str(dest)]) == 0
    capsys.readouterr()
    assert cli.main(["db", "restore", "--yes", str(dest)]) == 0
    out = capsys.readouterr().out
    assert str(dest) in out
    assert str(tmp_path / "cli.db") in out


def test_restore_without_a_live_file_does_not_need_yes(
    db_settings: KeelSettings,
    tmp_path: Path,
) -> None:
    cli.db_upgrade()
    dest = tmp_path / "copy.db"
    assert cli.main(["db", "backup", str(dest)]) == 0
    (tmp_path / "cli.db").unlink()
    assert cli.main(["db", "restore", str(dest)]) == 0
    assert (tmp_path / "cli.db").is_file()


def test_restore_refuses_an_existing_live_file_without_yes(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.db_upgrade()
    dest = tmp_path / "copy.db"
    assert cli.main(["db", "backup", str(dest)]) == 0
    capsys.readouterr()
    assert cli.main(["db", "restore", str(dest)]) == 1
    err = capsys.readouterr().err
    assert "--yes" in err
    assert str(tmp_path / "cli.db") in err


def test_restore_refuses_a_missing_source(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.db"
    assert cli.main(["db", "restore", str(missing)]) == 1
    err = capsys.readouterr().err
    assert "No backup at" in err
    assert str(missing) in err


def test_restore_refuses_a_non_sqlite_source(
    db_settings: KeelSettings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    junk = tmp_path / "junk.db"
    junk.write_text("not a database", encoding="utf-8")
    assert cli.main(["db", "restore", str(junk)]) == 1
    assert "Not a SQLite database" in capsys.readouterr().err
