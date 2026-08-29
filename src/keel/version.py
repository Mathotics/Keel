"""Runtime version is always the installed distribution, which is defined in pyproject.toml."""

from importlib.metadata import version

DISTRIBUTION_NAME = "keel"


def package_version() -> str:
    """Return the Keel version from package metadata (sourced from pyproject.toml)."""
    return version(DISTRIBUTION_NAME)
