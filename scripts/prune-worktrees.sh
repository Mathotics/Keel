#!/usr/bin/env bash
# Remove merged and stale git worktrees and their local branches.
# Usage:
#   ./scripts/prune-worktrees.sh [--dry-run] [--stale] [--force]
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/prune-worktrees.sh [options]

With no options, remove every managed worktree whose branch is merged
into the default branch, and every local branch that is merged into the
default branch and is not checked out. A managed worktree lives under
<repository>.worktrees, the directory deploy-worktree creates.

A branch counts as merged when its tip is contained in the local default
branch, or in origin/<default> when that remote-tracking ref exists.
Squash merges are not detected. Remote branches are left in place.

The default branch and the main checkout are never removed. A worktree
this command was started from is left in place. Run it from any checkout.

Options:
  --stale                   Also select worktrees and branches whose tip
                            commit is at least --stale-days old
  --stale-days <days>       Age threshold for --stale (default: 90).
                            Passing this turns --stale on
  --skip-merged             Do not remove items only because they are merged
  --worktrees-only          Do not delete local branches that have no
                            managed worktree
  --force                   Discard uncommitted changes, unlock a locked
                            worktree, and delete an unmerged branch selected
                            by --stale
  -n, --dry-run             Print what would be removed and change nothing
  -v, --verbose             Explain why each worktree and branch was kept
  -h, --help                Show this help
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
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

count_phrase() {
  if [[ "$1" -eq 1 ]]; then
    printf '1 %s' "$2"
  else
    printf '%s %s' "$1" "$3"
  fi
}

DRY_RUN=0
VERBOSE=0
FORCE=0
INCLUDE_STALE=0
SKIP_MERGED=0
WORKTREES_ONLY=0
STALE_DAYS=90

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --stale)
      INCLUDE_STALE=1
      shift
      ;;
    --skip-merged)
      SKIP_MERGED=1
      shift
      ;;
    --worktrees-only)
      WORKTREES_ONLY=1
      shift
      ;;
    --stale-days)
      [[ $# -ge 2 ]] || die "--stale-days requires a value"
      [[ "$2" =~ ^[0-9]+$ ]] || die "--stale-days must be a positive integer"
      STALE_DAYS=$((10#$2))
      [[ "${STALE_DAYS}" -ge 1 ]] || die "--stale-days must be a positive integer"
      INCLUDE_STALE=1
      shift 2
      ;;
    --*)
      die "unknown option: $1"
      ;;
    *)
      die "unexpected argument: $1"
      ;;
  esac
done

if [[ "${SKIP_MERGED}" -eq 1 && "${INCLUDE_STALE}" -eq 0 ]]; then
  die "--skip-merged removes nothing unless --stale is set"
fi
command -v git >/dev/null 2>&1 || die "git is required"

ORIGINAL_PWD="$(pwd)"
START_TOP=""
START_COMMON=""
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  START_TOP="$(git rev-parse --show-toplevel)"
  START_COMMON="$(git rev-parse --git-common-dir)"
  if [[ "${START_COMMON}" != /* && "${START_COMMON}" != [A-Za-z]:* ]]; then
    START_COMMON="${START_TOP}/${START_COMMON}"
  fi
fi

cleanup() {
  cd "${ORIGINAL_PWD}" || true
}
trap cleanup EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
git rev-parse --git-dir >/dev/null 2>&1 || die "prune-worktrees must run inside a git repository"

GIT_COMMON="$(git rev-parse --git-common-dir)"
GIT_COMMON="$(cd "${GIT_COMMON}" && pwd)"
MAIN_REPO="$(cd "${GIT_COMMON}/.." && pwd)"
if [[ -n "${START_COMMON}" ]] && ! paths_equal "${START_COMMON}" "${GIT_COMMON}"; then
  START_TOP=""
fi
cd "${MAIN_REPO}"

DEFAULT_BRANCH="main"
if ORIGIN_HEAD="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null)"; then
  DEFAULT_BRANCH="${ORIGIN_HEAD#refs/remotes/origin/}"
fi
git show-ref --verify --quiet -- "refs/heads/${DEFAULT_BRANCH}" || die "default branch '${DEFAULT_BRANCH}' does not exist locally"
ORIGIN_DEFAULT=""
if git show-ref --verify --quiet -- "refs/remotes/origin/${DEFAULT_BRANCH}"; then
  ORIGIN_DEFAULT="origin/${DEFAULT_BRANCH}"
fi

WORKTREES_PARENT="${MAIN_REPO}.worktrees"
NOW_EPOCH="$(date +%s)"
REMOVED_WORKTREES=0
REMOVED_BRANCHES=0
SKIPPED=0
FAILED=0

contained_in_default() {
  local rev="$1"
  if git merge-base --is-ancestor -- "${rev}" "${DEFAULT_BRANCH}"; then
    return 0
  fi
  if [[ -n "${ORIGIN_DEFAULT}" ]] && git merge-base --is-ancestor -- "${rev}" "${ORIGIN_DEFAULT}"; then
    return 0
  fi
  return 1
}

tip_epoch() {
  local rev="$1" epoch
  epoch="$(git log -1 --format=%ct "${rev}" 2>/dev/null || true)"
  if [[ "${epoch}" =~ ^[0-9]+$ ]]; then
    printf '%s' "${epoch}"
  fi
}

age_days() {
  local epoch="$1" age
  age=$(( (NOW_EPOCH - epoch) / 86400 ))
  if [[ "${age}" -lt 0 ]]; then
    age=0
  fi
  printf '%s' "${age}"
}

worktree_dirty() {
  local dirty
  dirty="$(git -C "$1" status --porcelain)"
  [[ -n "${dirty}" ]]
}

WT_PATH=()
WT_BRANCH=()
WT_HEAD=()
WT_DETACHED=()
WT_LOCKED=()

flush_worktree() {
  [[ -n "${CUR_PATH:-}" ]] || return 0
  WT_PATH+=("${CUR_PATH}")
  WT_BRANCH+=("${CUR_BRANCH:-}")
  WT_HEAD+=("${CUR_HEAD:-}")
  WT_DETACHED+=("${CUR_DETACHED:-0}")
  WT_LOCKED+=("${CUR_LOCKED:-0}")
}

CUR_PATH=""
CUR_BRANCH=""
CUR_HEAD=""
CUR_DETACHED=0
CUR_LOCKED=0
if ! worktree_list="$(git worktree list --porcelain)"; then
  die "git worktree list failed"
fi
while IFS= read -r line || [[ -n "${line}" ]]; do
  case "${line}" in
    worktree\ *)
      flush_worktree
      CUR_PATH="${line#worktree }"
      CUR_BRANCH=""
      CUR_HEAD=""
      CUR_DETACHED=0
      CUR_LOCKED=0
      ;;
    HEAD\ *)
      CUR_HEAD="${line#HEAD }"
      ;;
    branch\ *)
      CUR_BRANCH="${line#branch }"
      ;;
    detached)
      CUR_DETACHED=1
      ;;
    locked*)
      CUR_LOCKED=1
      ;;
  esac
done <<< "${worktree_list}"
flush_worktree

CHECKED_OUT=$'\n'
CLAIMED=$'\n'
ACTION_KIND=()
ACTION_PATH=()
ACTION_BRANCH=()
ACTION_REASON=()
ACTION_MERGED=()
ACTION_LOCKED=()

short_branch() {
  local ref="$1"
  printf '%s' "${ref#refs/heads/}"
}

is_listed() {
  local list="$1" name="$2"
  case "${list}" in
    *$'\n'"${name}"$'\n'*) return 0 ;;
    *) return 1 ;;
  esac
}

add_action() {
  ACTION_KIND+=("$1")
  ACTION_PATH+=("$2")
  ACTION_BRANCH+=("$3")
  ACTION_REASON+=("$4")
  ACTION_MERGED+=("$5")
  ACTION_LOCKED+=("$6")
}

wt_index=0
while [[ "${wt_index}" -lt "${#WT_PATH[@]}" ]]; do
  path="${WT_PATH[${wt_index}]}"
  ref="${WT_BRANCH[${wt_index}]}"
  head="${WT_HEAD[${wt_index}]}"
  locked="${WT_LOCKED[${wt_index}]}"
  short=""
  if [[ -n "${ref}" ]]; then
    short="$(short_branch "${ref}")"
    CHECKED_OUT+="${short}"$'\n'
  fi
  wt_index=$((wt_index + 1))
done

wt_index=0
while [[ "${wt_index}" -lt "${#WT_PATH[@]}" ]]; do
  path="${WT_PATH[${wt_index}]}"
  ref="${WT_BRANCH[${wt_index}]}"
  head="${WT_HEAD[${wt_index}]}"
  locked="${WT_LOCKED[${wt_index}]}"
  short=""
  if [[ -n "${ref}" ]]; then
    short="$(short_branch "${ref}")"
  fi
  label="${short}"
  if [[ -z "${label}" ]]; then
    label="detached"
  fi

  if paths_equal "${path}" "${MAIN_REPO}"; then
    [[ "${VERBOSE}" -eq 1 ]] && echo "keep worktree ${path}: main checkout"
    wt_index=$((wt_index + 1))
    continue
  fi
  if ! path_is_inside "${WORKTREES_PARENT}" "${path}"; then
    [[ "${VERBOSE}" -eq 1 ]] && echo "keep worktree ${path}: outside ${WORKTREES_PARENT}"
    wt_index=$((wt_index + 1))
    continue
  fi
  if [[ -n "${START_TOP}" ]] && paths_equal "${path}" "${START_TOP}"; then
    [[ "${VERBOSE}" -eq 1 ]] && echo "keep worktree ${path}: this command was started here"
    wt_index=$((wt_index + 1))
    continue
  fi

  rev="${short}"
  if [[ -z "${rev}" ]]; then
    rev="${head}"
  fi
  if [[ -z "${rev}" ]]; then
    [[ "${VERBOSE}" -eq 1 ]] && echo "keep worktree ${path}: no branch or commit"
    wt_index=$((wt_index + 1))
    continue
  fi
  if [[ "${short}" == "${DEFAULT_BRANCH}" ]]; then
    [[ "${VERBOSE}" -eq 1 ]] && echo "keep worktree ${path}: default branch"
    wt_index=$((wt_index + 1))
    continue
  fi

  merged=0
  if contained_in_default "${rev}"; then
    merged=1
  fi
  epoch="$(tip_epoch "${rev}")"
  age=""
  stale=0
  if [[ -n "${epoch}" ]]; then
    age="$(age_days "${epoch}")"
    if [[ "${age}" -ge "${STALE_DAYS}" ]]; then
      stale=1
    fi
  fi
  reason=""
  if [[ "${SKIP_MERGED}" -eq 0 && "${merged}" -eq 1 ]]; then
    reason="merged into ${DEFAULT_BRANCH}"
  elif [[ "${INCLUDE_STALE}" -eq 1 && "${stale}" -eq 1 ]]; then
    reason="stale, ${age} days"
  fi
  if [[ -z "${reason}" ]]; then
    if [[ "${VERBOSE}" -eq 1 ]]; then
      age_text="unknown age"
      [[ -n "${age}" ]] && age_text="last commit ${age} days ago"
      merged_text="not merged"
      [[ "${merged}" -eq 1 ]] && merged_text="merged into ${DEFAULT_BRANCH}"
      echo "keep worktree ${path} (${label}): ${merged_text}, ${age_text}"
    fi
    wt_index=$((wt_index + 1))
    continue
  fi

  dirty=0
  if worktree_dirty "${path}"; then
    dirty=1
  fi
  blockers=""
  [[ "${dirty}" -eq 1 ]] && blockers="uncommitted changes"
  if [[ "${locked}" -eq 1 ]]; then
    if [[ -n "${blockers}" ]]; then
      blockers="${blockers}, locked"
    else
      blockers="locked"
    fi
  fi
  if [[ "${merged}" -eq 0 ]]; then
    if [[ -n "${blockers}" ]]; then
      blockers="${blockers}, not merged into ${DEFAULT_BRANCH}"
    else
      blockers="not merged into ${DEFAULT_BRANCH}"
    fi
  fi
  if [[ -n "${blockers}" && "${FORCE}" -eq 0 ]]; then
    echo "skip: worktree ${path} branch ${label}: ${blockers}; re-run with --force"
    SKIPPED=$((SKIPPED + 1))
    wt_index=$((wt_index + 1))
    continue
  fi

  if [[ -n "${short}" ]]; then
    CLAIMED+="${short}"$'\n'
  fi
  add_action "worktree" "${path}" "${short}" "${reason}" "${merged}" "${locked}"
  wt_index=$((wt_index + 1))
done

if [[ "${WORKTREES_ONLY}" -eq 0 ]]; then
  branch_list="$(git for-each-ref --format='%(refname:short)' refs/heads)" || die "git for-each-ref failed"
  while IFS= read -r name; do
    [[ -n "${name}" ]] || continue
    if is_listed "${CLAIMED}" "${name}"; then
      continue
    fi
    if [[ "${name}" == "${DEFAULT_BRANCH}" ]]; then
      [[ "${VERBOSE}" -eq 1 ]] && echo "keep branch ${name}: default branch"
      continue
    fi
    if is_listed "${CHECKED_OUT}" "${name}"; then
      [[ "${VERBOSE}" -eq 1 ]] && echo "keep branch ${name}: checked out"
      continue
    fi
    merged=0
    if contained_in_default "${name}"; then
      merged=1
    fi
    epoch="$(tip_epoch "${name}")"
    age=""
    stale=0
    if [[ -n "${epoch}" ]]; then
      age="$(age_days "${epoch}")"
      if [[ "${age}" -ge "${STALE_DAYS}" ]]; then
        stale=1
      fi
    fi
    reason=""
    if [[ "${SKIP_MERGED}" -eq 0 && "${merged}" -eq 1 ]]; then
      reason="merged into ${DEFAULT_BRANCH}"
    elif [[ "${INCLUDE_STALE}" -eq 1 && "${stale}" -eq 1 ]]; then
      reason="stale, ${age} days"
    fi
    if [[ -z "${reason}" ]]; then
      if [[ "${VERBOSE}" -eq 1 ]]; then
        age_text="unknown age"
        [[ -n "${age}" ]] && age_text="last commit ${age} days ago"
        merged_text="not merged"
        [[ "${merged}" -eq 1 ]] && merged_text="merged into ${DEFAULT_BRANCH}"
        echo "keep branch ${name}: ${merged_text}, ${age_text}"
      fi
      continue
    fi
    if [[ "${merged}" -eq 0 && "${FORCE}" -eq 0 ]]; then
      echo "skip: branch ${name}: not merged into ${DEFAULT_BRANCH}; re-run with --force"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    add_action "branch" "" "${name}" "${reason}" "${merged}" "0"
  done <<< "${branch_list}"
fi

delete_branch() {
  local name="$1" merged="$2" reason="$3" status
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "dry-run: delete branch ${name} - ${reason}"
    REMOVED_BRANCHES=$((REMOVED_BRANCHES + 1))
    return 0
  fi
  echo "Deleting branch ${name} - ${reason}..."
  status=0
  if [[ "${merged}" -eq 1 ]]; then
    git branch -d -- "${name}" || git branch -D -- "${name}" || status=1
  else
    git branch -D -- "${name}" || status=1
  fi
  if [[ "${status}" -ne 0 ]]; then
    return 1
  fi
  REMOVED_BRANCHES=$((REMOVED_BRANCHES + 1))
  return 0
}

action_index=0
while [[ "${action_index}" -lt "${#ACTION_KIND[@]}" ]]; do
  kind="${ACTION_KIND[${action_index}]}"
  path="${ACTION_PATH[${action_index}]}"
  branch="${ACTION_BRANCH[${action_index}]}"
  reason="${ACTION_REASON[${action_index}]}"
  merged="${ACTION_MERGED[${action_index}]}"
  locked="${ACTION_LOCKED[${action_index}]}"
  if [[ "${kind}" == "worktree" ]]; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      echo "dry-run: remove worktree ${path} - ${reason}"
    else
      echo "Removing worktree ${path} - ${reason}..."
      if [[ "${FORCE}" -eq 1 && "${locked}" -eq 1 ]]; then
        if ! git worktree unlock -- "${path}"; then
          echo "error: git worktree unlock failed for ${path}" >&2
          FAILED=1
          action_index=$((action_index + 1))
          continue
        fi
      fi
      if [[ "${FORCE}" -eq 1 ]]; then
        if ! git worktree remove --force -- "${path}"; then
          echo "error: git worktree remove failed for ${path}" >&2
          FAILED=1
          action_index=$((action_index + 1))
          continue
        fi
      else
        if ! git worktree remove -- "${path}"; then
          echo "error: git worktree remove failed for ${path}" >&2
          FAILED=1
          action_index=$((action_index + 1))
          continue
        fi
      fi
    fi
    REMOVED_WORKTREES=$((REMOVED_WORKTREES + 1))
    if [[ -n "${branch}" ]]; then
      if ! delete_branch "${branch}" "${merged}" "${reason}"; then
        echo "error: git branch delete failed for ${branch}" >&2
        FAILED=1
      fi
    fi
  else
    if ! delete_branch "${branch}" "${merged}" "${reason}"; then
      echo "error: git branch delete failed for ${branch}" >&2
      FAILED=1
    fi
  fi
  action_index=$((action_index + 1))
done

if [[ "${DRY_RUN}" -eq 0 && -d "${WORKTREES_PARENT}" ]]; then
  find "${WORKTREES_PARENT}" -depth -type d -empty -delete || true
fi

echo
worktree_phrase="$(count_phrase "${REMOVED_WORKTREES}" "worktree" "worktrees")"
branch_phrase="$(count_phrase "${REMOVED_BRANCHES}" "branch" "branches")"
if [[ "${REMOVED_WORKTREES}" -eq 0 && "${REMOVED_BRANCHES}" -eq 0 ]]; then
  echo "Nothing to remove."
elif [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Would remove ${worktree_phrase} and ${branch_phrase}."
else
  echo "Removed ${worktree_phrase} and ${branch_phrase}."
fi
if [[ "${SKIPPED}" -gt 0 ]]; then
  echo "Skipped $(count_phrase "${SKIPPED}" "item" "items")."
fi
echo "Remote branches were left in place."

if [[ "${FAILED}" -ne 0 ]]; then
  exit 1
fi
