import tomllib
from pathlib import Path

from keel.version import package_version


def test_package_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert package_version() == data["project"]["version"]
