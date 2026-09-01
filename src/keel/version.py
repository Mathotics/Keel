"""Runtime version is the installed distribution, which pyproject.toml defines."""

from importlib.metadata import version

DISTRIBUTION_NAME = "keel"


def package_version() -> str:
    """Return the Keel version from package metadata (sourced from pyproject.toml)."""
    return version(DISTRIBUTION_NAME)
