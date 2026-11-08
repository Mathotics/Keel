import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module() -> Any:
    path = ROOT / "scripts" / "version_tag.py"
    spec = importlib.util.spec_from_file_location("version_tag", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


version_tag: Any = _module()


def test_bump_rules() -> None:
    base = (2, 5, 7)
    assert version_tag.next_version(base, "major") == (3, 0, 0)
    assert version_tag.next_version(base, "minor") == (2, 6, 0)
    assert version_tag.next_version(base, "patch") == (2, 5, 8)


def test_missing_label_means_minor_and_two_labels_fail() -> None:
    assert version_tag.bump_kind(["bug"]) == "minor"
    assert version_tag.bump_kind(["bump:patch", "docs"]) == "patch"
    with pytest.raises(ValueError):
        version_tag.bump_kind(["bump:major", "bump:minor"])


def test_label_check_ignores_pull_requests_into_other_branches() -> None:
    names = ["bump:major", "bump:patch"]
    assert (
        version_tag.label_error(names, base_ref="feature", default_branch="main")
        is None
    )
    assert (
        version_tag.label_error(names, base_ref="main", default_branch="main")
        is not None
    )


def test_plan_publish_introduces_without_bump_and_then_bumps() -> None:
    assert (
        version_tag.plan_publish(
            base=None,
            head_tagged=False,
            merged=True,
            labels=["bump:major"],
            initial="3.2.1",
        )
        == "v3.2.1"
    )
    assert (
        version_tag.plan_publish(
            base=(3, 2, 1),
            head_tagged=False,
            merged=True,
            labels=[],
            initial="3.2.1",
        )
        == "v3.3.0"
    )
    assert (
        version_tag.plan_publish(
            base=(3, 2, 1),
            head_tagged=True,
            merged=True,
            labels=["bump:patch"],
            initial="3.2.1",
        )
        is None
    )
    assert (
        version_tag.plan_publish(
            base=(3, 2, 1),
            head_tagged=False,
            merged=False,
            labels=["bump:major"],
            initial="3.2.1",
        )
        is None
    )


def test_initial_version_file_is_a_release() -> None:
    text = (ROOT / ".github" / "initial-version").read_text(encoding="utf-8").strip()
    assert version_tag.RELEASE.match(text)


def test_merged_pull_request_requires_the_default_branch() -> None:
    pulls = [
        {"merged_at": None, "base": {"ref": "main"}, "labels": []},
        {"merged_at": "2026-11-06T00:00:00Z", "base": {"ref": "dev"}, "labels": []},
    ]
    assert version_tag.merged_pull_request(pulls, "main") is None
    pulls.append(
        {
            "merged_at": "2026-11-06T00:00:00Z",
            "base": {"ref": "main"},
            "labels": [{"name": "bump:patch"}],
        }
    )
    found = version_tag.merged_pull_request(pulls, "main")
    assert found is not None
    assert version_tag.label_names(found) == ["bump:patch"]


def _git(root: Path, *args: str) -> str:
    output = version_tag.git(root, *args).stdout
    if not isinstance(output, str):
        raise AssertionError("git stdout was not text")
    return output.strip()


def _repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "version-test@example.com")
    _git(path, "config", "user.name", "Version Test")
    (path / "f").write_text("a\n", encoding="utf-8")
    _git(path, "add", "f")
    _git(path, "commit", "-m", "a")
    return path


def test_scm_version_keeps_tag_numbers_and_uses_the_short_hash(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    _git(root, "tag", "v1.4.8")
    short = _git(root, "rev-parse", "--short", "HEAD")
    # packaging.version.Version drops a leading zero from an all-digit local
    # segment, so 0631373 would become 631373. The version keeps git's hash.
    assert version_tag.scm_version(root) == f"1.4.8+{short}"

    (root / "f").write_text("b\n", encoding="utf-8")
    _git(root, "add", "f")
    _git(root, "commit", "-m", "b")
    ahead_short = _git(root, "rev-parse", "--short", "HEAD")
    ahead = version_tag.scm_version(root)
    assert ahead == f"1.4.8+{ahead_short}"
    assert version_tag.closest_version_tag(root) == "v1.4.8"

    (root / "f").write_text("dirty\n", encoding="utf-8")
    assert version_tag.scm_version(root) == ahead


def _seed(root: Path, version: str) -> None:
    github = root / ".github"
    github.mkdir()
    (github / "initial-version").write_text(f"{version}\n", encoding="utf-8")


def test_scm_version_uses_the_seed_when_the_repository_has_no_tag(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path / "untagged")
    _seed(root, "4.5.6")
    short = _git(root, "rev-parse", "--short", "HEAD")
    assert version_tag.scm_version(root) == str(Version(f"4.5.6+{short}"))
    assert _git(root, "tag", "--list") == ""


def test_scm_version_uses_the_seed_when_the_only_tag_is_not_an_ancestor(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path / "before-tag")
    _seed(root, "1.0.0")
    parent = _git(root, "rev-parse", "HEAD")
    (root / "f").write_text("b\n", encoding="utf-8")
    _git(root, "add", "f")
    _git(root, "commit", "-m", "b")
    tagged = _git(root, "rev-parse", "HEAD")
    _git(root, "tag", "v1.0.0")
    _git(root, "checkout", "--detach", parent)
    short = _git(root, "rev-parse", "--short", "HEAD")
    assert version_tag.closest_version_tag(root) is None
    assert version_tag.scm_version(root) == str(Version(f"1.0.0+{short}"))
    version_tag.ensure_local(root)
    assert _git(root, "rev-parse", "v1.0.0") == tagged
    assert version_tag.tag_on_head(root) is False


def test_ensure_local_tags_the_seed_once(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    seed = root / ".github"
    seed.mkdir()
    (seed / "initial-version").write_text("9.8.7\n", encoding="utf-8")
    version_tag.ensure_local(root)
    assert version_tag.tag_on_head(root)
    assert version_tag.closest_version_tag(root) == "v9.8.7"
    version_tag.ensure_local(root)
    assert version_tag.closest_version_tag(root) == "v9.8.7"
