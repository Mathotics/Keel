# Package version

The **only** place the Keel version number is written is `[project].version` in [`pyproject.toml`](../pyproject.toml).

Runtime and UI code must read it from installed package metadata (`importlib.metadata.version("keel")` via `keel.version.package_version`). Do not copy the version into `__init__.py`, FastAPI constructors, HTML, tests, or docs as a literal.

After you bump `pyproject.toml`, reinstall the editable package (`pip install -e ".[dev]"`) so metadata matches.

See [ADR 002](adr/ADR-002.md).
