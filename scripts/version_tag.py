"""Publish and read Keel versions from git tags.

Major, minor, and patch come from the closest ``vMAJOR.MINOR.PATCH`` tag
reachable from this commit. The build is the short commit hash.
``.github/initial-version`` supplies those three numbers when no such tag
is reachable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / ".github" / "initial-version"
VERSION_TAG = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
RELEASE = re.compile(r"^\d+\.\d+\.\d+$")
TAG_REGEX = r"^v(?P<version>\d+\.\d+\.\d+)$"
BUMP_LABELS = ("bump:major", "bump:minor", "bump:patch")
PEP440_LOCAL = re.compile(r"^\d+\.\d+\.\d+\+[0-9a-f]+$")


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # A commit hook exports GIT_DIR and GIT_INDEX_FILE. Those would make
    # `git -C` operate on the repository being committed instead of `root`.
    kept = {"GIT_EXEC_PATH", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_TERMINAL_PROMPT"}
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") or key in kept
    }
    result = subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"git {' '.join(args)} failed: {detail}")
    return result


def parse_tag(tag: str) -> tuple[int, int, int]:
    match = VERSION_TAG.match(tag)
    if match is None:
        raise ValueError(f"{tag} is not a version tag")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def load_initial(root: Path | None = None) -> str:
    override = os.environ.get("KEEL_INITIAL_VERSION", "").strip()
    if override:
        text = override
    else:
        seed = (root or ROOT) / ".github" / "initial-version"
        text = seed.read_text(encoding="utf-8").strip()
    if not RELEASE.match(text):
        raise SystemExit("initial version must be MAJOR.MINOR.PATCH")
    return text


def bump_labels(names: list[str]) -> list[str]:
    return [name for name in names if name in BUMP_LABELS]


def bump_kind(names: list[str]) -> str:
    found = bump_labels(names)
    if len(found) > 1:
        joined = ", ".join(found)
        raise ValueError(
            "only one of bump:major, bump:minor, and bump:patch may be set, "
            f"found {joined}"
        )
    if not found:
        return "minor"
    return found[0].split(":", 1)[1]


def label_error(names: list[str], *, base_ref: str, default_branch: str) -> str | None:
    if base_ref != default_branch:
        return None
    try:
        bump_kind(names)
    except ValueError as exc:
        return str(exc)
    return None


def next_version(base: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    major, minor, patch = base
    if kind == "major":
        return (major + 1, 0, 0)
    if kind == "minor":
        return (major, minor + 1, 0)
    if kind == "patch":
        return (major, minor, patch + 1)
    raise ValueError(f"unknown bump {kind}")


def plan_publish(
    *,
    base: tuple[int, int, int] | None,
    head_tagged: bool,
    merged: bool,
    labels: list[str],
    initial: str,
) -> str | None:
    """Return the tag to publish, or None when this commit must not move it."""
    if not merged or head_tagged:
        return None
    if base is None:
        if not RELEASE.match(initial):
            raise ValueError("initial version must be MAJOR.MINOR.PATCH")
        return f"v{initial}"
    major, minor, patch = next_version(base, bump_kind(labels))
    return f"v{major}.{minor}.{patch}"


def closest_version_tag(root: Path) -> str | None:
    listed = git(root, "tag", "--merged", "HEAD", "--list").stdout.splitlines()
    best_rank: tuple[int, tuple[int, int, int]] | None = None
    best_tag: str | None = None
    for raw in listed:
        tag = raw.strip()
        if not VERSION_TAG.match(tag):
            continue
        distance = int(git(root, "rev-list", "--count", f"{tag}..HEAD").stdout.strip())
        parsed = parse_tag(tag)
        rank = (distance, tuple(-part for part in parsed))
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_tag = tag
    return best_tag


def tag_on_head(root: Path) -> bool:
    listed = git(root, "tag", "--points-at", "HEAD").stdout.splitlines()
    return any(VERSION_TAG.match(tag.strip()) for tag in listed)


def local_hash(version: object) -> str:
    """setuptools-scm local scheme: always ``+`` and ``git rev-parse --short``."""
    config = getattr(version, "config", None)
    root = getattr(config, "absolute_root", None)
    if root is None:
        root = Path.cwd()
    short = git(Path(root), "rev-parse", "--short", "HEAD").stdout.strip()
    return f"+{short}"


def scm_version(root: Path | None = None) -> str:
    """Version string for this checkout.

    The closest reachable version tag supplies the three numbers. A checkout
    whose history does not contain one uses ``.github/initial-version``.
    The local part is always this commit's short hash.
    """
    root = root or ROOT
    short = git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    version: object
    if closest_version_tag(root) is None:
        version = f"{load_initial(root)}+{short}"
    else:
        version = _version_from_scm(root)
    if not isinstance(version, str) or not PEP440_LOCAL.match(version):
        raise SystemExit(
            "The reachable version tag did not produce MAJOR.MINOR.PATCH+<short hash>."
        )
    return version


def _version_from_scm(root: Path) -> object:
    import warnings

    import setuptools_scm

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*tag_regex.*")
        return setuptools_scm.get_version(
            root=root,
            version_scheme="only-version",
            local_scheme=local_hash,
            tag_regex=TAG_REGEX,
        )


def merged_pull_request(
    pulls: list[dict[str, Any]], default_branch: str
) -> dict[str, Any] | None:
    for pull in pulls:
        base = pull.get("base") or {}
        if pull.get("merged_at") and base.get("ref") == default_branch:
            return pull
    return None


def label_names(pull: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for label in pull.get("labels") or []:
        if isinstance(label, str):
            names.append(label)
        elif isinstance(label, dict) and label.get("name"):
            names.append(str(label["name"]))
    return names


def _github_json(path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "keel-version-tag",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def _pulls_for_sha(repo: str, sha: str, token: str) -> list[dict[str, Any]]:
    payload = _github_json(f"/repos/{repo}/commits/{sha}/pulls", token)
    if not isinstance(payload, list):
        raise SystemExit("GitHub did not return a pull request list")
    return payload


def _default_branch(repo: str, token: str) -> str:
    payload = _github_json(f"/repos/{repo}", token)
    branch = payload.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise SystemExit("GitHub did not return the default branch")
    return branch


def _sha(root: Path) -> str:
    configured = os.environ.get("GITHUB_SHA", "").strip()
    if configured:
        return configured
    return git(root, "rev-parse", "HEAD").stdout.strip()


def needs_tag_status(root: Path | None = None) -> int:
    """0 when a merged pull request still needs its tag, 1 when it does not.

    A GitHub request error returns 0 so deploy waits instead of baking the
    previous numbers. Pull request builds return 1.
    """
    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        return 1
    root = root or ROOT
    if tag_on_head(root):
        return 1
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return 1
    try:
        sha = _sha(root)
        pulls = _pulls_for_sha(repo, sha, token)
        branch = _default_branch(repo, token)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, SystemExit):
        return 0
    if merged_pull_request(pulls, branch) is None:
        return 1
    return 0


def _create_tag(root: Path, tag: str, *, push: bool) -> None:
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    existing = git(root, "rev-parse", "--verify", f"refs/tags/{tag}", check=False)
    if existing.returncode == 0:
        if existing.stdout.strip() == head:
            return
        raise SystemExit(f"{tag} already points at another commit")
    git(root, "tag", tag, head)
    if push:
        git(root, "push", "origin", f"refs/tags/{tag}")


def ensure_local(root: Path | None = None) -> None:
    root = root or ROOT
    if closest_version_tag(root) is not None:
        return
    tag = f"v{load_initial(root)}"
    existing = git(root, "rev-parse", "--verify", f"refs/tags/{tag}", check=False)
    if existing.returncode == 0:
        return
    _create_tag(root, tag, push=False)


def publish(root: Path | None = None) -> None:
    root = root or ROOT
    if tag_on_head(root):
        print("version tag already points at this commit")
        return
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        raise SystemExit("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
    sha = _sha(root)
    pulls = _pulls_for_sha(repo, sha, token)
    branch = _default_branch(repo, token)
    pull = merged_pull_request(pulls, branch)
    if pull is None:
        print("not a merged pull request; version tag unchanged")
        return
    base_tag = closest_version_tag(root)
    base = None if base_tag is None else parse_tag(base_tag)
    try:
        planned = plan_publish(
            base=base,
            head_tagged=False,
            merged=True,
            labels=label_names(pull),
            initial=load_initial(root),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if planned is None:
        return
    _create_tag(root, planned, push=True)
    print(planned)


def wait_for_tag(root: Path | None = None) -> int:
    root = root or ROOT
    for _ in range(60):
        git(root, "fetch", "--force", "origin", "+refs/tags/*:refs/tags/*", check=False)
        if tag_on_head(root):
            print("version tag is on this commit")
            return 0
        if needs_tag_status(root) == 1:
            print("this commit does not need a new version tag")
            return 0
        print("waiting for the version tag", flush=True)
        time.sleep(5)
    print("version tag was not published", file=sys.stderr)
    return 1


def _label_payload(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("PR_LABELS is not JSON") from exc
    if not isinstance(data, list):
        raise SystemExit("PR_LABELS must be a JSON list")
    names: list[str] = []
    for item in data:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def check_labels() -> int:
    raw = os.environ.get("PR_LABELS")
    base = os.environ.get("BASE_REF", "")
    default = os.environ.get("DEFAULT_BRANCH", "")
    if raw is None or not base or not default:
        raise SystemExit("PR_LABELS, BASE_REF, and DEFAULT_BRANCH are required")
    error = label_error(_label_payload(raw), base_ref=base, default_branch=default)
    if error:
        print(error, file=sys.stderr)
        return 1
    print("bump labels are valid")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keel version tags")
    parser.add_argument(
        "command",
        choices=(
            "check-labels",
            "describe",
            "ensure-local",
            "needs-tag",
            "publish",
            "tag-on-head",
            "wait-for-tag",
        ),
    )
    args = parser.parse_args(argv)
    if args.command == "check-labels":
        return check_labels()
    if args.command == "describe":
        print(scm_version())
        return 0
    if args.command == "ensure-local":
        ensure_local()
        return 0
    if args.command == "needs-tag":
        return needs_tag_status()
    if args.command == "publish":
        publish()
        return 0
    if args.command == "tag-on-head":
        return 0 if tag_on_head(ROOT) else 1
    return wait_for_tag()


if __name__ == "__main__":
    raise SystemExit(main())
