#!/usr/bin/env bash
# One-time production bootstrap on the Raspberry Pi.
# Installs Python 3.12, a production venv, data directory, user systemd unit, and starts Keel.
# Later updates use scripts/deploy-prod.sh via GitHub Actions. Do not run this on every deploy.
set -euo pipefail

PROD_ROOT="${KEEL_PROD_ROOT:-/mnt/library/Keel}"
DATA_DIR="${KEEL_DATA_DIR:-/mnt/library/keel-data}"
ENV_FILE="${KEEL_ENV_FILE:-${DATA_DIR}/keel.env}"
ENV_EXAMPLE="${PROD_ROOT}/deploy/keel.env.example"
UNIT_SRC="${PROD_ROOT}/deploy/keel.service"
UNIT_NAME="${KEEL_UNIT_NAME:-keel}"
UNIT_DST="${HOME}/.config/systemd/user/${UNIT_NAME}.service"
HEALTH_URL="${KEEL_HEALTH_URL:-http://127.0.0.1:8000/health}"
HEALTH_ATTEMPTS="${KEEL_HEALTH_ATTEMPTS:-30}"
MIN_PY="3.12"

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

export_user_systemd() {
  local uid
  uid="$(id -u)"
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${uid}}"
  export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
}

python_is_ok() {
  "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >/dev/null 2>&1
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if [[ -x "${HOME}/.local/bin/uv" ]]; then
    export PATH="${HOME}/.local/bin:${PATH}"
    return 0
  fi
  command -v curl >/dev/null 2>&1 || die "curl is required to install uv"
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
  command -v uv >/dev/null 2>&1 || die "uv installed but not on PATH"
}

ensure_pip() {
  local py="${PROD_ROOT}/.venv/bin/python"
  if "${py}" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  ensure_uv
  log "Installing pip into the production venv"
  if uv pip install --python "${py}" pip setuptools wheel; then
    return 0
  fi
  "${py}" -m ensurepip --upgrade
  "${py}" -m pip --version >/dev/null 2>&1 || die "pip is not available in the production venv"
}

ensure_python312() {
  local py="${PROD_ROOT}/.venv/bin/python"
  if [[ -x "${py}" ]] && python_is_ok "${py}"; then
    log "Production venv already has Python ${MIN_PY}+"
    ensure_pip
    return 0
  fi
  ensure_uv
  log "Installing Python ${MIN_PY} with uv"
  uv python install "${MIN_PY}"
  if [[ -d "${PROD_ROOT}/.venv" ]]; then
    log "Replacing existing venv that is not Python ${MIN_PY}+"
    rm -rf "${PROD_ROOT}/.venv"
  fi
  uv venv --seed --python "${MIN_PY}" "${PROD_ROOT}/.venv"
  python_is_ok "${PROD_ROOT}/.venv/bin/python" || die "venv Python is not ${MIN_PY}+"
  ensure_pip
}

ensure_linger() {
  local user
  user="$(id -un)"
  if loginctl show-user "${user}" -p Linger --value 2>/dev/null | grep -qx yes; then
    return 0
  fi
  log "Enabling lingering for ${user}"
  if loginctl enable-linger "${user}"; then
    return 0
  fi
  if sudo -n loginctl enable-linger "${user}"; then
    return 0
  fi
  die "could not enable linger for ${user} (needed so user systemd survives logout)"
}

wait_for_health() {
  local i
  command -v curl >/dev/null 2>&1 || die "curl is required for the health check"
  for ((i = 1; i <= HEALTH_ATTEMPTS; i++)); do
    if curl -sf "${HEALTH_URL}" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

[[ -d "${PROD_ROOT}/.git" ]] || die "production checkout not found: ${PROD_ROOT}"
[[ -f "${ENV_EXAMPLE}" ]] || die "missing ${ENV_EXAMPLE}"
[[ -f "${UNIT_SRC}" ]] || die "missing ${UNIT_SRC}"

cd "${PROD_ROOT}"
ensure_python312

VENV_PY="${PROD_ROOT}/.venv/bin/python"
log "Upgrading pip"
"${VENV_PY}" -m pip install --upgrade pip setuptools wheel
log "Installing Keel (production extras only)"
"${VENV_PY}" -m pip install -e "${PROD_ROOT}"

mkdir -p "${DATA_DIR}"
if [[ ! -f "${ENV_FILE}" ]]; then
  tr -d '\r' < "${ENV_EXAMPLE}" > "${ENV_FILE}"
  log "Wrote ${ENV_FILE}"
else
  tmp="$(mktemp)"
  tr -d '\r' < "${ENV_FILE}" > "${tmp}"
  cat "${tmp}" > "${ENV_FILE}"
  rm -f "${tmp}"
  log "Keeping existing ${ENV_FILE}"
fi

set -a
# shellcheck disable=SC1090
source <(tr -d '\r' < "${ENV_FILE}")
set +a

log "Applying database migrations"
"${VENV_PY}" -m keel db upgrade

mkdir -p "$(dirname "${UNIT_DST}")"
tr -d '\r' < "${UNIT_SRC}" > "${UNIT_DST}"
export_user_systemd
ensure_linger
systemctl --user daemon-reload
systemctl --user enable --now "${UNIT_NAME}.service"

if ! wait_for_health; then
  die "service started but ${HEALTH_URL} did not become healthy"
fi

log "Bootstrap complete; ${HEALTH_URL} is healthy"
log "Later deploys are automatic from main via GitHub Actions"
