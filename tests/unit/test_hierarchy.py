import pytest

from keel.domain.enums import IssueType
from keel.domain.errors import (
    InvalidParentError,
    InvalidParentTypeError,
    ParentCycleError,
)
from keel.domain.hierarchy import IssueRef, check_children, check_parent, child_type_of

EPIC = IssueType.EPIC
STORY = IssueType.STORY
SUBTASK = IssueType.SUBTASK


def ref(issue_id: int, type: IssueType, project_id: int = 1) -> IssueRef:
    return IssueRef(id=issue_id, type=type, project_id=project_id)


@pytest.mark.parametrize("type", [EPIC, STORY, SUBTASK])
def test_no_parent_is_always_legal(type: IssueType) -> None:
    check_parent(ref(1, type), None)


@pytest.mark.parametrize(
    ("child", "parent"),
    [(STORY, EPIC), (SUBTASK, STORY)],
)
def test_legal_pairs_are_accepted(child: IssueType, parent: IssueType) -> None:
    check_parent(ref(2, child), ref(1, parent))


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (EPIC, EPIC),
        (EPIC, STORY),
        (EPIC, SUBTASK),
        (STORY, STORY),
        (STORY, SUBTASK),
        (SUBTASK, EPIC),
        (SUBTASK, SUBTASK),
    ],
)
def test_illegal_pairs_are_refused(child: IssueType, parent: IssueType) -> None:
    with pytest.raises(InvalidParentTypeError) as caught:
        check_parent(ref(2, child), ref(1, parent))
    assert caught.value.code == "issue.invalid_parent_type"


def test_parent_must_share_the_project() -> None:
    with pytest.raises(InvalidParentError) as caught:
        check_parent(ref(2, STORY, project_id=1), ref(1, EPIC, project_id=2))
    assert caught.value.code == "issue.invalid_parent"


def test_project_is_checked_before_type() -> None:
    with pytest.raises(InvalidParentError):
        check_parent(ref(2, SUBTASK, project_id=1), ref(1, EPIC, project_id=2))


def test_an_issue_cannot_parent_itself() -> None:
    with pytest.raises(ParentCycleError) as caught:
        check_parent(ref(1, SUBTASK), ref(1, STORY))
    assert caught.value.code == "issue.parent_cycle"


def test_an_issue_cannot_sit_under_its_own_descendant() -> None:
    with pytest.raises(ParentCycleError):
        check_parent(ref(1, SUBTASK), ref(3, STORY), ancestor_ids=[2, 1])


def test_an_unsaved_issue_has_no_cycle_to_close() -> None:
    check_parent(IssueRef(id=None, type=SUBTASK, project_id=1), ref(3, STORY), [2, 1])


def test_a_type_change_is_refused_by_existing_children() -> None:
    with pytest.raises(InvalidParentTypeError):
        check_children(EPIC, [SUBTASK])


def test_child_type_follows_the_parent_rules() -> None:
    assert child_type_of(EPIC) is STORY
    assert child_type_of(STORY) is SUBTASK
    assert child_type_of(SUBTASK) is None


def test_a_type_change_its_children_allow_is_accepted() -> None:
    check_children(STORY, [SUBTASK, SUBTASK])


def test_a_childless_issue_may_change_type_freely() -> None:
    check_children(SUBTASK, [])
