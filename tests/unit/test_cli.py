import pytest

from keel.cli import main


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_no_command_prints_help() -> None:
    assert main([]) == 0


def test_serve_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["serve", "--help"])
    assert excinfo.value.code == 0
