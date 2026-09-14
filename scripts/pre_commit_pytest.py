"""Run the coverage pytest suite using the project virtualenv when present."""

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
            "--cov=keel",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
            *sys.argv[1:],
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
