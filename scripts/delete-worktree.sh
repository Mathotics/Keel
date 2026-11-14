#!/usr/bin/env bash
# Remove a git worktree and its local branch created by deploy-worktree.
# Usage:
#   ./scripts/delete-worktree.sh <branch> [--force]
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/delete-worktree.sh <branch> [options]

Required:
  <branch>                  Name of the branch / worktree directory to remove

Options:
  --force                   Discard uncommitted changes and delete the branch
                            even if it is not fully merged
  -h, --help                Show this help

The worktree path is <repository>.worktrees/<branch>, the same place
deploy-worktree creates it. The local branch is deleted with the worktree.
A remote branch is left in place. Run this script from the main checkout.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

safe_branch_name() {
  local name="$1" rest segment
  [[ -n "${name}" ]] || return 1
  [[ "${name}" != -* ]] || return 1
  [[ "${name}" != /* ]] || return 1
  [[ "${name}" != *//* ]] || return 1
  [[ "${name}" != */ ]] || return 1
  rest="${name}"
  while [[ -n "${rest}" ]]; do
    segment="${rest%%/*}"
    [[ -n "${segment}" && "${segment}" != "." && "${segment}" != ".." ]] || return 1
    if [[ "${rest}" == */* ]]; then
      rest="${rest#*/}"
    else
      rest=""
    fi
  done
  return 0
}

to_git_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

normalize_path() {
  local path
  path="$(to_git_path "$1")"
  path="${path%/}"
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      printf '%s' "${path}" | tr '[:upper:]' '[:lower:]'
      ;;
    *)
      printf '%s' "${path}"
      ;;
  esac
}

paths_equal() {
  [[ "$(normalize_path "$1")" == "$(normalize_path "$2")" ]]
}

path_is_inside() {
  local parent child
  parent="$(normalize_path "$1")"
  child="$(normalize_path "$2")"
  [[ "${child}" == "${parent}/"* ]]
}

branch_exists() {
  git show-ref --verify --quiet -- "refs/heads/$1" 2>/dev/null
}

branch_merged() {
  local name="$1" upstream
  if git merge-base --is-ancestor -- "${name}" HEAD; then
    return 0
  fi
  if upstream="$(git rev-parse --abbrev-ref -- "${name}@{upstream}" 2>/dev/null)"; then
    if git merge-base --is-ancestor -- "${name}" "${upstream}"; then
      return 0
    fi
  fi
  return 1
}

BRANCH_NAME=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --*)
      die "unknown option: $1"
      ;;
    *)
      [[ -z "${BRANCH_NAME}" ]] || die "unexpected argument: $1"
      BRANCH_NAME="$1"
      shift
      ;;
  esac
done

[[ -n "${BRANCH_NAME}" ]] || { usage; die "branch name is required"; }
command -v git >/dev/null 2>&1 || die "git is required"

GIT_BRANCH="${BRANCH_NAME//\\//}"
safe_branch_name "${GIT_BRANCH}" || die "invalid branch name: ${BRANCH_NAME}"
BRANCH_REF="refs/heads/${GIT_BRANCH}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_PWD="$(pwd)"

cleanup() {
  cd "${ORIGINAL_PWD}" || true
}
trap cleanup EXIT

cd "${SCRIPT_DIR}/.."
git rev-parse --git-dir >/dev/null 2>&1 || die "delete-worktree must run inside the Keel git repository"

GIT_COMMON="$(git rev-parse --git-common-dir)"
GIT_COMMON="$(cd "${GIT_COMMON}" && pwd)"
MAIN_REPO="$(cd "${GIT_COMMON}/.." && pwd)"
TOP_LEVEL="$(cd "$(git rev-parse --show-toplevel)" && pwd)"
[[ "${TOP_LEVEL}" == "${MAIN_REPO}" ]] || die "run this script from the main repository checkout (${MAIN_REPO}), not a linked worktree"
cd "${MAIN_REPO}"

DEFAULT_BRANCH="main"
if ORIGIN_HEAD="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null)"; then
  DEFAULT_BRANCH="${ORIGIN_HEAD#refs/remotes/origin/}"
fi
[[ "${GIT_BRANCH}" != "${DEFAULT_BRANCH}" ]] || die "refusing to delete the default branch '${DEFAULT_BRANCH}'"

CURRENT_BRANCH="$(git branch --show-current || true)"
[[ "${CURRENT_BRANCH}" != "${GIT_BRANCH}" ]] || die "branch '${GIT_BRANCH}' is checked out in the main repository"

WORKTREES_PARENT="${MAIN_REPO}.worktrees"
RELATIVE="${GIT_BRANCH}"
WORKTREE_PATH="${WORKTREES_PARENT}/${RELATIVE}"
path_is_inside "${WORKTREES_PARENT}" "${WORKTREE_PATH}" || die "refusing to touch a path outside ${WORKTREES_PARENT}"
GIT_WORKTREE_PATH="$(to_git_path "${WORKTREE_PATH}")"

MATCHED=0
MATCH_BRANCH=""
MATCH_DETACHED=0
CHECKOUT_PATH=""
CUR_PATH=""
CUR_BRANCH=""
CUR_DETACHED=0

consider_worktree() {
  [[ -n "${CUR_PATH}" ]] || return 0
  if paths_equal "${CUR_PATH}" "${GIT_WORKTREE_PATH}"; then
    MATCHED=1
    MATCH_BRANCH="${CUR_BRANCH}"
    MATCH_DETACHED="${CUR_DETACHED}"
  fi
  if [[ "${CUR_BRANCH}" == "${BRANCH_REF}" ]]; then
    CHECKOUT_PATH="${CUR_PATH}"
  fi
}

if ! worktree_list="$(git worktree list --porcelain)"; then
  die "git worktree list failed"
fi
while IFS= read -r line; do
  case "${line}" in
    worktree\ *)
      consider_worktree
      CUR_PATH="${line#worktree }"
      CUR_BRANCH=""
      CUR_DETACHED=0
      ;;
    branch\ *)
      CUR_BRANCH="${line#branch }"
      ;;
    detached)
      CUR_DETACHED=1
      ;;
  esac
done <<< "${worktree_list}"
consider_worktree

REMOVED_WORKTREE=0
if branch_exists "${GIT_BRANCH}"; then
  BRANCH_EXISTS=1
else
  BRANCH_EXISTS=0
fi

if [[ "${MATCHED}" -eq 1 ]]; then
  if [[ "${MATCH_DETACHED}" -eq 1 || -z "${MATCH_BRANCH}" ]]; then
    die "worktree at ${GIT_WORKTREE_PATH} is detached; expected branch '${GIT_BRANCH}'"
  fi
  if [[ "${MATCH_BRANCH}" != "${BRANCH_REF}" ]]; then
    other="${MATCH_BRANCH#refs/heads/}"
    die "worktree at ${GIT_WORKTREE_PATH} is on '${other}', not '${GIT_BRANCH}'"
  fi
  if [[ "${FORCE}" -eq 0 ]]; then
    dirty="$(git -C "${GIT_WORKTREE_PATH}" status --porcelain)"
    [[ -z "${dirty}" ]] || die "worktree has uncommitted changes; re-run with --force to discard them"
  fi
  if [[ "${BRANCH_EXISTS}" -eq 1 && "${FORCE}" -eq 0 ]] && ! branch_merged "${GIT_BRANCH}"; then
    die "branch '${GIT_BRANCH}' is not fully merged; re-run with --force to delete it"
  fi
  echo "Removing worktree at ${GIT_WORKTREE_PATH}..."
  if [[ "${FORCE}" -eq 1 ]]; then
    git worktree remove --force -- "${GIT_WORKTREE_PATH}"
  else
    git worktree remove -- "${GIT_WORKTREE_PATH}"
  fi
  REMOVED_WORKTREE=1
else
  if [[ -e "${WORKTREE_PATH}" ]]; then
    die "path exists but is not a registered git worktree: ${GIT_WORKTREE_PATH}"
  fi
  if [[ -n "${CHECKOUT_PATH}" ]]; then
    die "branch '${GIT_BRANCH}' is checked out at ${CHECKOUT_PATH}, not at ${GIT_WORKTREE_PATH}"
  fi
  if [[ "${BRANCH_EXISTS}" -eq 0 ]]; then
    die "no worktree or local branch named '${GIT_BRANCH}'"
  fi
  if [[ "${FORCE}" -eq 0 ]] && ! branch_merged "${GIT_BRANCH}"; then
    die "branch '${GIT_BRANCH}' is not fully merged; re-run with --force to delete it"
  fi
  echo "Worktree path already absent: ${GIT_WORKTREE_PATH}"
fi

if [[ "${BRANCH_EXISTS}" -eq 1 ]]; then
  echo "Deleting local branch '${GIT_BRANCH}'..."
  if [[ "${FORCE}" -eq 1 ]]; then
    git branch -D -- "${GIT_BRANCH}"
  else
    git branch -d -- "${GIT_BRANCH}"
  fi
fi

if [[ -d "${WORKTREES_PARENT}" ]]; then
  rmdir "${WORKTREES_PARENT}" 2>/dev/null || true
fi

echo
if [[ "${REMOVED_WORKTREE}" -eq 1 ]]; then
  echo "Worktree removed: ${GIT_WORKTREE_PATH}"
fi
if [[ "${BRANCH_EXISTS}" -eq 1 ]]; then
  echo "Branch deleted: ${GIT_BRANCH}"
fi
echo "Remote branches were left in place."
