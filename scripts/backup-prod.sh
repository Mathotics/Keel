#!/usr/bin/env bash
# Copy the production SQLite database onto the backup mount.
# Run on the production Raspberry Pi. Does not restart Keel.
set -euo pipefail

PROD_ROOT="${KEEL_PROD_ROOT:-/mnt/library/Keel}"
DATA_DIR="${KEEL_DATA_DIR:-/mnt/library/keel-data}"
ENV_FILE="${KEEL_ENV_FILE:-${DATA_DIR}/keel.env}"
BACKUP_MOUNT="${KEEL_BACKUP_MOUNT:-/mnt/library-backup}"
BACKUP_DIR="${KEEL_BACKUP_DIR:-${BACKUP_MOUNT}/keel-data}"

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
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

destination_for() {
  case "$1" in
    daily) printf '%s\n' "${BACKUP_DIR}/keel.db" ;;
    weekly) printf '%s\n' "${BACKUP_DIR}/keel-weekly.db" ;;
    monthly) printf '%s\n' "${BACKUP_DIR}/keel-monthly.db" ;;
    *)
      die "usage: backup-prod.sh daily|weekly|monthly"
      ;;
  esac
}

require_backup_mount() {
  case "${BACKUP_DIR}" in
    "${BACKUP_MOUNT}" | "${BACKUP_MOUNT}"/*) ;;
    *) return 0 ;;
  esac
  if command -v mountpoint >/dev/null 2>&1; then
    mountpoint -q "${BACKUP_MOUNT}" || die "backup mount is not mounted: ${BACKUP_MOUNT}"
  elif [[ ! -d "${BACKUP_MOUNT}" ]]; then
    die "backup mount missing: ${BACKUP_MOUNT}"
  fi
}

main() {
  local cadence dest py
  cadence="${1:-}"
  [[ -n "${cadence}" ]] || die "usage: backup-prod.sh daily|weekly|monthly"
  dest="$(destination_for "${cadence}")"
  py="$(venv_python)"
  [[ -x "${py}" ]] || die "production venv missing; run scripts/bootstrap-prod.sh once"

  require_backup_mount
  load_prod_env
  cd "${PROD_ROOT}"
  log "Writing ${cadence} backup to ${dest}"
  "${py}" -m keel db backup --yes "${dest}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
