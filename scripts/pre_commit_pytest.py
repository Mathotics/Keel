"""Run the unit tests using the project virtualenv when present.

The full suite, including the 90% coverage gate, stays on ``poe test`` and in
CI. This hook is what ``git commit`` waits on, so it runs only the unit tests.
"""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHONS = (
    _ROOT / ".venv" / "Scripts" / "python.exe",
    _ROOT / ".venv" / "bin" / "python",
)


def _python() -> Path:
    for candidate in _VENV_PYTHONS:
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def main() -> int:
    return subprocess.call(
        [
            str(_python()),
            "-m",
            "pytest",
            "tests/unit",
            "-m",
            "unit",
            *sys.argv[1:],
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
