#!/usr/bin/env bash
# Create a git worktree for a new branch, onboard it, and optionally run an agent.
# Usage:
#   ./scripts/deploy-worktree.sh <branch>
#       [--skip-main-check] [--stash-switch]
#       [--agent-command <cmd>] [--commit-when-done <msg>] [--push-when-done]
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy-worktree.sh <branch> [options]

Required:
  <branch>                  Name of the new branch / worktree directory

Options:
  --skip-main-check         Skip verifying the main checkout is on the default branch
  --stash-switch            If not on the default branch: stash, checkout default, then restore after
  --agent-command <cmd>     After onboard, activate .venv and run: agent <cmd>
  --commit-when-done <msg>  In the worktree: git add --all && git commit -m <msg>
  --push-when-done          In the worktree: git push -u origin HEAD
  -h, --help                Show this help
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

BRANCH_NAME=""
SKIP_MAIN_CHECK=0
STASH_SWITCH=0
AGENT_COMMAND=""
COMMIT_WHEN_DONE=""
PUSH_WHEN_DONE=0
HAVE_AGENT=0
HAVE_COMMIT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --skip-main-check)
      SKIP_MAIN_CHECK=1
      shift
      ;;
    --stash-switch)
      STASH_SWITCH=1
      shift
      ;;
    --push-when-done)
      PUSH_WHEN_DONE=1
      shift
      ;;
    --agent-command)
      [[ $# -ge 2 ]] || die "--agent-command requires a value"
      AGENT_COMMAND="$2"
      HAVE_AGENT=1
      shift 2
      ;;
    --commit-when-done)
      [[ $# -ge 2 ]] || die "--commit-when-done requires a value"
      COMMIT_WHEN_DONE="$2"
      HAVE_COMMIT=1
      shift 2
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
if [[ "${SKIP_MAIN_CHECK}" -eq 1 && "${STASH_SWITCH}" -eq 1 ]]; then
  die "--skip-main-check and --stash-switch cannot be used together"
fi
command -v git >/dev/null 2>&1 || die "git is required"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_PWD="$(pwd)"
cd "${SCRIPT_DIR}/.."

git rev-parse --git-dir >/dev/null 2>&1 || die "deploy-worktree must run inside the Keel git repository"

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

PREVIOUS_BRANCH=""
DID_STASH=0
STASH_MESSAGE="deploy-worktree:auto-stash"
WORKTREE_PATH=""

restore_main_checkout() {
  if [[ -z "${PREVIOUS_BRANCH}" ]]; then
    return 0
  fi
  echo "Restoring branch '${PREVIOUS_BRANCH}'..."
  if ! git checkout "${PREVIOUS_BRANCH}"; then
    echo "warning: failed to checkout previous branch '${PREVIOUS_BRANCH}'" >&2
    return 0
  fi
  if [[ "${DID_STASH}" -eq 1 ]]; then
    echo "Restoring stashed changes..."
    if ! git stash pop; then
      echo "warning: git stash pop failed; stash may still be on the stack" >&2
    fi
  fi
}

cleanup() {
  cd "${MAIN_REPO}" || true
  restore_main_checkout || true
  cd "${ORIGINAL_PWD}" || true
}
trap cleanup EXIT

# Step 0 / 0a / 0b
if [[ "${SKIP_MAIN_CHECK}" -eq 0 ]]; then
  CURRENT_BRANCH="$(git branch --show-current)"
  [[ -n "${CURRENT_BRANCH}" ]] || die "detached HEAD; check out '${DEFAULT_BRANCH}' (or pass --skip-main-check / --stash-switch)"
  if [[ "${CURRENT_BRANCH}" != "${DEFAULT_BRANCH}" ]]; then
    if [[ "${STASH_SWITCH}" -eq 0 ]]; then
      die "main checkout is on '${CURRENT_BRANCH}', expected '${DEFAULT_BRANCH}' (use --stash-switch or --skip-main-check)"
    fi
    echo "Not on '${DEFAULT_BRANCH}' (on '${CURRENT_BRANCH}'); stashing and switching..."
    PREVIOUS_BRANCH="${CURRENT_BRANCH}"
    STASH_OUT="$(git stash push -u -m "${STASH_MESSAGE}" 2>&1)" || die "git stash failed: ${STASH_OUT}"
    if [[ "${STASH_OUT}" != *"No local changes to save"* ]]; then
      DID_STASH=1
    fi
    git checkout "${DEFAULT_BRANCH}"
  fi
fi

# Step 1
echo "Fetching and updating '${DEFAULT_BRANCH}'..."
git fetch origin
git pull --ff-only "origin" "${DEFAULT_BRANCH}"

# Step 2
WORKTREES_PARENT="${MAIN_REPO}.worktrees"
WORKTREE_PATH="${WORKTREES_PARENT}/${BRANCH_NAME}"
[[ ! -e "${WORKTREE_PATH}" ]] || die "worktree path already exists: ${WORKTREE_PATH}"
mkdir -p "${WORKTREES_PARENT}"
echo "Creating worktree at ${WORKTREE_PATH} (branch '${BRANCH_NAME}')..."
git worktree add "${WORKTREE_PATH}" -b "${BRANCH_NAME}"

# Steps 3–7
cd "${WORKTREE_PATH}"

echo "Running onboard..."
./scripts/onboard.sh

if [[ "${HAVE_AGENT}" -eq 1 ]]; then
  echo "Activating virtual environment..."
  if [[ -f .venv/bin/activate ]]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
  elif [[ -f .venv/Scripts/activate ]]; then
    # shellcheck source=/dev/null
    source .venv/Scripts/activate
  else
    die "venv activate script not found under .venv"
  fi
  echo "Running agent: agent ${AGENT_COMMAND}"
  # Intentional word-splitting / shell parsing so flags in --agent-command work.
  # shellcheck disable=SC2086
  eval "agent ${AGENT_COMMAND}"
fi

if [[ "${HAVE_COMMIT}" -eq 1 ]]; then
  echo "Committing worktree changes..."
  git add --all
  git commit -m "${COMMIT_WHEN_DONE}"
fi

if [[ "${PUSH_WHEN_DONE}" -eq 1 ]]; then
  echo "Pushing worktree branch..."
  git push -u origin HEAD
fi

# cleanup trap returns to main repo / original pwd and restores stash
trap - EXIT
cleanup

echo
echo "Worktree ready: ${WORKTREE_PATH}"
echo "Branch: ${BRANCH_NAME}"
