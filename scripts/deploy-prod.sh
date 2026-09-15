#!/usr/bin/env bash
# Update /mnt/library/Keel to GITHUB_SHA, migrate SQLite, and restart Keel.
# Run on the production Raspberry Pi. Does not use the Actions _work tree as the live checkout.
set -euo pipefail

PROD_ROOT="${KEEL_PROD_ROOT:-/mnt/library/Keel}"
DATA_DIR="${KEEL_DATA_DIR:-/mnt/library/keel-data}"
ENV_FILE="${KEEL_ENV_FILE:-${DATA_DIR}/keel.env}"
HEALTH_URL="${KEEL_HEALTH_URL:-http://127.0.0.1:8000/health}"
HEALTH_ATTEMPTS="${KEEL_HEALTH_ATTEMPTS:-30}"
UNIT_NAME="${KEEL_UNIT_NAME:-keel}"

PREVIOUS_SHA=""
BACKUP_PATH=""
RESTARTED=0

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

load_prod_env() {
  [[ -f "${ENV_FILE}" ]] || die "missing production env file: ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source <(tr -d '\r' < "${ENV_FILE}")
  set +a
}

venv_python() {
  printf '%s\n' "${PROD_ROOT}/.venv/bin/python"
}

keel_cmd() {
  "$(venv_python)" -m keel "$@"
}

install_prod() {
  local py
  py="$(venv_python)"
  [[ -x "${py}" ]] || return 1
  "${py}" -m pip install -e "${PROD_ROOT}"
}

fetch_and_reset() {
  local remote
  if [[ -n "${GITHUB_TOKEN:-}" && -n "${GITHUB_REPOSITORY:-}" ]]; then
    git -C "${PROD_ROOT}" -c "http.extraHeader=Authorization: Bearer ${GITHUB_TOKEN}" \
      fetch --force "https://github.com/${GITHUB_REPOSITORY}.git" "${GITHUB_SHA}"
  else
    git -C "${PROD_ROOT}" fetch --force origin "${GITHUB_SHA}"
  fi
  git -C "${PROD_ROOT}" checkout --force -B main "${GITHUB_SHA}"
  git -C "${PROD_ROOT}" reset --hard "${GITHUB_SHA}"
}

reset_to_sha() {
  git -C "${PROD_ROOT}" checkout --force -B main "$1"
  git -C "${PROD_ROOT}" reset --hard "$1"
}

backup_db() {
  BACKUP_PATH="${DATA_DIR}/pre-deploy-${PREVIOUS_SHA}.db"
  keel_cmd db backup --yes "${BACKUP_PATH}"
}

upgrade_db() {
  keel_cmd db upgrade
}

restore_db() {
  [[ -n "${BACKUP_PATH}" && -f "${BACKUP_PATH}" ]] || return 0
  keel_cmd db restore --yes "${BACKUP_PATH}"
}

restart_unit() {
  export_user_systemd
  systemctl --user restart "${UNIT_NAME}.service"
  RESTARTED=1
}

wait_for_health() {
  local i
  command -v curl >/dev/null 2>&1 || return 1
  for ((i = 1; i <= HEALTH_ATTEMPTS; i++)); do
    if curl -sf "${HEALTH_URL}" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

revert_code() {
  log "Reverting checkout to ${PREVIOUS_SHA}"
  reset_to_sha "${PREVIOUS_SHA}"
  install_prod
}

fail_keep_process() {
  printf 'error: %s\n' "$*" >&2
  revert_code
  restore_db
  log "Left the running service untouched"
  exit 1
}

fail_after_restart() {
  printf 'error: %s\n' "$*" >&2
  revert_code
  restore_db
  restart_unit || true
  wait_for_health || true
  exit 1
}

[[ -n "${GITHUB_SHA:-}" ]] || die "GITHUB_SHA is not set"
[[ -d "${PROD_ROOT}/.git" ]] || die "production checkout not found: ${PROD_ROOT}"
[[ -x "$(venv_python)" ]] || die "production venv missing; run scripts/bootstrap-prod.sh once"

export_user_systemd
load_prod_env
cd "${PROD_ROOT}"

PREVIOUS_SHA="$(git -C "${PROD_ROOT}" rev-parse HEAD)"
log "Current HEAD ${PREVIOUS_SHA}; deploying ${GITHUB_SHA}"

if ! fetch_and_reset; then
  die "git update to ${GITHUB_SHA} failed; checkout unchanged"
fi

if ! install_prod; then
  fail_keep_process "pip install failed"
fi

if ! backup_db; then
  fail_keep_process "database backup failed"
fi

if ! upgrade_db; then
  fail_keep_process "database upgrade failed"
fi

if ! restart_unit; then
  fail_after_restart "systemctl restart ${UNIT_NAME} failed"
fi

if ! wait_for_health; then
  fail_after_restart "health check failed at ${HEALTH_URL}"
fi

log "Deployed ${GITHUB_SHA}; ${HEALTH_URL} is healthy"
