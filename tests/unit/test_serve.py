import argparse
from unittest.mock import MagicMock

import pytest

from keel.cli import main, serve


def test_serve_passes_overrides_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    run = MagicMock()
    monkeypatch.setattr("keel.cli.uvicorn.run", run)
    args = argparse.Namespace(
        host="0.0.0.0",
        port=9000,
        reload=True,
        log_level="debug",
    )
    assert serve(args) == 0
    run.assert_called_once()
    kwargs = run.call_args.kwargs
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9000
    assert kwargs["reload"] is True
    assert kwargs["log_level"] == "debug"
    assert kwargs["factory"] is True


def test_serve_uses_settings_when_flags_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel.settings import get_settings

    get_settings.cache_clear()
    run = MagicMock()
    monkeypatch.setattr("keel.cli.uvicorn.run", run)
    args = argparse.Namespace(host=None, port=None, reload=False, log_level=None)
    assert serve(args) == 0
    kwargs = run.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8000
    assert kwargs["reload"] is False
    assert kwargs["log_level"] == "info"


def test_unknown_command_exits() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["not-a-command"])
    assert excinfo.value.code != 0
