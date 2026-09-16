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

# GitHub git-over-HTTPS wants Basic x-access-token (as actions/checkout does),
# not Bearer. An empty credential helper plus GIT_TERMINAL_PROMPT=0 stops the
# Pi from prompting for a username and failing with "No such device or address".
github_basic_extraheader() {
  local b64
  if command -v openssl >/dev/null 2>&1; then
    b64="$(printf 'x-access-token:%s' "${GITHUB_TOKEN}" | openssl base64 -A)"
  else
    b64="$(
      python3 -c 'import base64, os; print(base64.b64encode(("x-access-token:" + os.environ["GITHUB_TOKEN"]).encode()).decode())'
    )"
  fi
  printf 'AUTHORIZATION: basic %s' "${b64}"
}

git_fetch() {
  local -a conf=( -c credential.helper= )
  while [[ "${1:-}" == -c ]]; do
    conf+=(-c "$2")
    shift 2
  done
  GIT_TERMINAL_PROMPT=0 git "${conf[@]}" -C "${PROD_ROOT}" fetch --force --update-shallow "$@"
}

fetch_from_workspace() {
  local workspace
  [[ -n "${GITHUB_WORKSPACE:-}" && -d "${GITHUB_WORKSPACE}/.git" ]] || return 1
  workspace="$(cd "${GITHUB_WORKSPACE}" && pwd)"
  log "Fetching ${GITHUB_SHA} from Actions workspace"
  git_fetch "${workspace}" "+HEAD:refs/keel-deploy/incoming"
}

fetch_from_github() {
  local header
  [[ -n "${GITHUB_TOKEN:-}" && -n "${GITHUB_REPOSITORY:-}" ]] || return 1
  header="$(github_basic_extraheader)"
  log "Fetching ${GITHUB_SHA} from GitHub"
  if git_fetch -c "http.https://github.com/.extraheader=${header}" \
    "https://github.com/${GITHUB_REPOSITORY}.git" \
    "+${GITHUB_SHA}:refs/keel-deploy/incoming"; then
    return 0
  fi
  git_fetch -c "http.https://github.com/.extraheader=${header}" \
    "https://github.com/${GITHUB_REPOSITORY}.git" \
    "+refs/heads/main:refs/remotes/origin/main"
}

fetch_from_origin() {
  log "Fetching ${GITHUB_SHA} from origin"
  git_fetch origin "+${GITHUB_SHA}:refs/keel-deploy/incoming" \
    || git_fetch origin "+refs/heads/main:refs/remotes/origin/main"
}

fetch_and_reset() {
  if fetch_from_workspace; then
    :
  elif fetch_from_github; then
    :
  elif fetch_from_origin; then
    :
  else
    return 1
  fi
  git -C "${PROD_ROOT}" checkout --force -B main "${GITHUB_SHA}" || return 1
  git -C "${PROD_ROOT}" reset --hard "${GITHUB_SHA}" || return 1
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

main() {
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
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main
fi
