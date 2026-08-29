import pytest

from keel.settings import KeelSettings, get_settings


def test_default_settings() -> None:
    settings = KeelSettings(_env_file=None)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.reload is False
    assert settings.log_level == "info"


def test_get_settings_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KEEL_HOST", "0.0.0.0")
    monkeypatch.setenv("KEEL_PORT", "9001")
    monkeypatch.setenv("KEEL_RELOAD", "true")
    monkeypatch.setenv("KEEL_LOG_LEVEL", "debug")
    settings = get_settings()
    assert settings.host == "0.0.0.0"
    assert settings.port == 9001
    assert settings.reload is True
    assert settings.log_level == "debug"
    get_settings.cache_clear()
