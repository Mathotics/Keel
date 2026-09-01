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
