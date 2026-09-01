import pytest

from keel.paths import (
    asset_path,
    assets_dir,
    copyright_notice,
    data_dir,
    database_path,
    license_path,
    license_text,
    migrations_dir,
    templates_dir,
)


def test_assets_dir_contains_favicon() -> None:
    assert (assets_dir() / "favicon.ico").is_file()


def test_asset_path_returns_existing_file() -> None:
    path = asset_path("favicon.ico")
    assert path.is_file()
    assert path.name == "favicon.ico"


def test_asset_path_missing_raises() -> None:
    with pytest.raises(FileNotFoundError, match="asset not found"):
        asset_path("does-not-exist.ico")


def test_assets_dir_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: False)
    with pytest.raises(FileNotFoundError, match="assets directory not found"):
        assets_dir()


def test_copyright_notice_comes_from_license_file() -> None:
    notice = copyright_notice()
    assert notice == license_text().splitlines()[0].strip()
    assert "copyright" in notice.lower()


def test_license_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pathlib.Path.is_file", lambda self: False)
    with pytest.raises(FileNotFoundError, match="LICENSE not found"):
        license_path()


def test_templates_dir_holds_the_base_template() -> None:
    assert (templates_dir() / "base.html").is_file()


def test_templates_dir_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: False)
    with pytest.raises(FileNotFoundError, match="templates directory not found"):
        templates_dir()


def test_migrations_dir_holds_the_alembic_environment() -> None:
    assert (migrations_dir() / "env.py").is_file()


def test_migrations_dir_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: False)
    with pytest.raises(FileNotFoundError, match="migrations directory not found"):
        migrations_dir()


def test_database_path_sits_in_the_data_directory() -> None:
    assert database_path().parent == data_dir()
    assert database_path().name == "keel.db"
