import os

import pytest

from keel.paths import database_path
from keel.settings import KeelSettings, get_settings


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_env_file=None` ignores the .env file but not the shell it runs in."""
    for name in [name for name in os.environ if name.startswith("KEEL_")]:
        monkeypatch.delenv(name)


@pytest.mark.usefixtures("unconfigured")
def test_default_settings() -> None:
    settings = KeelSettings(_env_file=None)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.reload is False
    assert settings.log_level == "info"
    assert settings.database_url is None
    assert settings.default_user is None


@pytest.mark.usefixtures("unconfigured")
def test_database_url_defaults_to_the_user_data_directory() -> None:
    settings = KeelSettings(_env_file=None)
    url = settings.resolved_database_url()
    assert url.startswith("sqlite+pysqlite:///")
    assert url.endswith(database_path().as_posix())


def test_database_url_honours_configuration() -> None:
    settings = KeelSettings(_env_file=None, database_url="sqlite://")
    assert settings.resolved_database_url() == "sqlite://"


def test_get_settings_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KEEL_HOST", "0.0.0.0")
    monkeypatch.setenv("KEEL_PORT", "9001")
    monkeypatch.setenv("KEEL_RELOAD", "true")
    monkeypatch.setenv("KEEL_LOG_LEVEL", "debug")
    monkeypatch.setenv("KEEL_DEFAULT_USER", "Ada")
    settings = get_settings()
    assert settings.host == "0.0.0.0"
    assert settings.port == 9001
    assert settings.reload is True
    assert settings.log_level == "debug"
    assert settings.default_user == "Ada"
    get_settings.cache_clear()
