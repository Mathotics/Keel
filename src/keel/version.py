"""Runtime version is the installed distribution, filled from git tags."""

from importlib.metadata import version

DISTRIBUTION_NAME = "keel"


def package_version() -> str:
    """Return the Keel version from package metadata generated from git tags."""
    return version(DISTRIBUTION_NAME)
