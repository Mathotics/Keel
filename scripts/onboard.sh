#!/usr/bin/env bash
# Onboard a local Keel development environment (venv + dependencies).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MIN_PY="3.12"

python_is_ok() {
  "$1" "${@:2}" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >/dev/null 2>&1
}

PY=()
if [[ -n "${PYTHON:-}" ]]; then
  if ! python_is_ok "${PYTHON}"; then
    echo "error: PYTHON=${PYTHON} is not Python ${MIN_PY} or newer" >&2
    exit 1
  fi
  PY=("${PYTHON}")
else
  found=0
  for candidate in "python3.12" "python3" "python"; do
    if command -v "${candidate}" >/dev/null 2>&1 && python_is_ok "${candidate}"; then
      PY=("${candidate}")
      found=1
      break
    fi
  done
  if [[ "${found}" -eq 0 ]] && command -v py >/dev/null 2>&1 && python_is_ok py -3.12; then
    PY=(py -3.12)
    found=1
  fi
  if [[ "${found}" -eq 0 ]]; then
    echo "error: Python ${MIN_PY} or newer is required (set PYTHON to a suitable interpreter)" >&2
    exit 1
  fi
fi

echo "Using Python: ${PY[*]}"
"${PY[@]}" -m venv .venv

if [[ -x .venv/bin/python ]]; then
  VENV_PY=".venv/bin/python"
elif [[ -x .venv/Scripts/python.exe ]]; then
  VENV_PY=".venv/Scripts/python.exe"
else
  echo "error: virtual environment Python was not created" >&2
  exit 1
fi

echo "Upgrading pip..."
"${VENV_PY}" -m pip install --upgrade pip setuptools wheel

echo "Installing package and development dependencies..."
"${VENV_PY}" -m pip install -e ".[dev]"

if [[ -x .venv/bin/poe ]]; then
  VENV_POE=".venv/bin/poe"
elif [[ -x .venv/Scripts/poe.exe ]]; then
  VENV_POE=".venv/Scripts/poe.exe"
else
  echo "error: poe was not installed into the virtual environment" >&2
  exit 1
fi

echo "Configuring Poe..."
"${VENV_POE}" _list

echo "Configuring pre-commit (git hooks and environments)..."
"${VENV_POE}" hooks

echo "Checking isort and mypy..."
"${VENV_POE}" isort-check
"${VENV_POE}" mypy

if [[ ! -f .env ]] && [[ -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

cat <<'EOF'

Onboarding complete.

Activate the virtual environment:
  Windows PowerShell:  .\.venv\Scripts\Activate.ps1
  Windows cmd:         .venv\Scripts\activate.bat
  Unix / Git Bash:     source .venv/bin/activate

Then run: poe serve
EOF
