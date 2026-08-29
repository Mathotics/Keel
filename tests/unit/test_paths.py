import pytest

from keel.paths import asset_path, assets_dir


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
