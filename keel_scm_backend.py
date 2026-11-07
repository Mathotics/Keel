"""Build backend that fills the package version from git before setuptools runs.

setuptools-scm reads the closest ``vMAJOR.MINOR.PATCH`` tag and this checkout's
short hash. The result is handed to setuptools as the pretend version so the
installed metadata matches that string, including when the commit is the tag.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _version_tag() -> object:
    path = ROOT / "scripts" / "version_tag.py"
    spec = importlib.util.spec_from_file_location("keel_version_tag", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prime() -> None:
    if os.environ.get("SETUPTOOLS_SCM_PRETEND_VERSION", "").strip():
        return
    module = _version_tag()
    os.environ["SETUPTOOLS_SCM_PRETEND_VERSION"] = module.scm_version(ROOT)


_prime()

from setuptools.build_meta import (  # noqa: E402
    build_editable,
    build_sdist,
    build_wheel,
    get_requires_for_build_editable,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
    prepare_metadata_for_build_editable,
    prepare_metadata_for_build_wheel,
)

__all__ = [
    "build_editable",
    "build_sdist",
    "build_wheel",
    "get_requires_for_build_editable",
    "get_requires_for_build_sdist",
    "get_requires_for_build_wheel",
    "prepare_metadata_for_build_editable",
    "prepare_metadata_for_build_wheel",
]
