import tomllib
from pathlib import Path

from packaging.version import Version

from keel.version import package_version

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_is_tag_plus_hash() -> None:
    parsed = Version(package_version())
    assert parsed.local is not None
    assert parsed.public.count(".") == 2
    assert parsed.is_prerelease is False


def test_pyproject_version_comes_from_git() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"]
    assert "version" in data["project"]["dynamic"]
