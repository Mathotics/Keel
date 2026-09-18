from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import (
    INITIAL_PRIORITY,
    INITIAL_STATUS,
    IssuePriority,
    IssueStatus,
    IssueType,
)
from keel.domain.errors import (
    DomainError,
    InvalidIssueError,
    InvalidParentError,
    InvalidParentTypeError,
    IssueHasChildrenError,
    NotFoundError,
    UserInUseError,
)
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.issues import IssueFilters


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def make(
    session: Session,
    project: Project,
    type: IssueType = IssueType.STORY,
    title: str = "Something",
    **kwargs: object,
) -> int:
    issue = issue_service.create_issue(
        session,
        project.id,
        type=type,
        title=title,
        **kwargs,  # type: ignore[arg-type]
    )
    return issue.id


def test_issues_are_numbered_per_project(session: Session, project: Project) -> None:
    other = project_service.create_project(session, "SITE", "Site")

    first = issue_service.get_issue(session, make(session, project))
    second = issue_service.get_issue(session, make(session, project))
    elsewhere = issue_service.get_issue(session, make(session, other))

    assert (first.number, second.number, elsewhere.number) == (1, 2, 1)


def test_an_issue_is_addressable_by_its_key(session: Session, project: Project) -> None:
    issue_id = make(session, project)
    issue = issue_service.get_issue(session, issue_id)

    assert issue_service.issue_key(issue, project) == "KEEL-1"
    assert issue_service.get_issue_by_key(session, "KEEL-1").id == issue_id


def test_a_deleted_number_is_never_reused(session: Session, project: Project) -> None:
    issue_service.delete_issue(session, make(session, project))
    replacement = issue_service.get_issue(session, make(session, project))
    assert replacement.number == 2


@pytest.mark.parametrize("key", ["KEEL-99", "KEEL", "NOPE-1", "KEEL-x"])
def test_unresolvable_keys_are_not_found(
    session: Session,
    project: Project,
    key: str,
) -> None:
    with pytest.raises(NotFoundError):
        issue_service.get_issue_by_key(session, key)


def test_issues_start_in_the_first_status(session: Session, project: Project) -> None:
    issue = issue_service.get_issue(session, make(session, project))
    assert issue.status is INITIAL_STATUS is IssueStatus.TODO
    assert issue.priority is INITIAL_PRIORITY is IssuePriority.P4


def test_priority_can_be_set_and_filtered(session: Session, project: Project) -> None:
    blocker = make(session, project, title="Blocker", priority=IssuePriority.P1)
    make(session, project, title="Ordinary")

    updated = issue_service.update_issue(
        session,
        blocker,
        priority=IssuePriority.P2,
    )
    assert updated.priority is IssuePriority.P2

    found = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(priority=IssuePriority.P2),
    )
    assert [issue.id for issue in found] == [blocker]


def test_cancelling_a_parent_leaves_children_unchanged(
    session: Session,
    project: Project,
) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = make(session, project, IssueType.STORY, "Story", parent_id=epic)
    issue_service.update_issue(session, epic, status=IssueStatus.CANCELLED)

    assert issue_service.get_issue(session, story).status is IssueStatus.TODO
    reopened = issue_service.update_issue(
        session,
        epic,
        status=IssueStatus.TODO,
    )
    assert reopened.status is IssueStatus.TODO


def test_a_blank_title_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(InvalidIssueError):
        make(session, project, title="  ")


def test_a_story_may_sit_under_an_epic(session: Session, project: Project) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = issue_service.get_issue(
        session,
        make(session, project, IssueType.STORY, "Story", parent_id=epic),
    )
    assert story.parent_id == epic


def test_a_subtask_under_an_epic_is_refused(
    session: Session,
    project: Project,
) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    with pytest.raises(InvalidParentTypeError) as caught:
        make(session, project, IssueType.SUBTASK, "Subtask", parent_id=epic)
    assert caught.value.code == "issue.invalid_parent_type"


def test_an_epic_with_a_parent_is_refused(session: Session, project: Project) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    with pytest.raises(InvalidParentTypeError):
        make(session, project, IssueType.EPIC, "Second", parent_id=epic)


def test_a_parent_in_another_project_is_refused(
    session: Session,
    project: Project,
) -> None:
    other = project_service.create_project(session, "SITE", "Site")
    foreign_epic = make(session, other, IssueType.EPIC, "Epic")

    with pytest.raises(InvalidParentError) as caught:
        make(session, project, IssueType.STORY, "Story", parent_id=foreign_epic)
    assert caught.value.code == "issue.invalid_parent"


def test_an_inverted_hierarchy_is_refused(session: Session, project: Project) -> None:
    """The type rules catch this before the cycle guard ever sees it.

    They also make a type-legal cycle unreachable, so the cycle guard is
    exercised directly in the hierarchy tests rather than through a service.
    """
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = make(session, project, IssueType.STORY, "Story", parent_id=epic)

    with pytest.raises(InvalidParentTypeError):
        issue_service.update_issue(session, epic, parent_id=story)


def test_an_issue_cannot_parent_itself(session: Session, project: Project) -> None:
    story = make(session, project, IssueType.STORY, "Story")

    with pytest.raises(DomainError):
        issue_service.update_issue(session, story, parent_id=story)


def test_a_parent_can_be_cleared(session: Session, project: Project) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = make(session, project, IssueType.STORY, "Story", parent_id=epic)

    updated = issue_service.update_issue(session, story, parent_id=None)
    assert updated.parent_id is None


def test_an_unmentioned_parent_survives_an_update(
    session: Session,
    project: Project,
) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = make(session, project, IssueType.STORY, "Story", parent_id=epic)

    updated = issue_service.update_issue(session, story, title="Renamed")
    assert updated.parent_id == epic


def test_a_type_change_its_children_forbid_is_refused(
    session: Session,
    project: Project,
) -> None:
    story = make(session, project, IssueType.STORY, "Story")
    make(session, project, IssueType.SUBTASK, "Subtask", parent_id=story)

    with pytest.raises(InvalidParentTypeError):
        issue_service.update_issue(session, story, type=IssueType.EPIC)


def test_a_type_change_its_parent_forbids_is_refused(
    session: Session,
    project: Project,
) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = make(session, project, IssueType.STORY, "Story", parent_id=epic)

    with pytest.raises(InvalidParentTypeError):
        issue_service.update_issue(session, story, type=IssueType.SUBTASK)


def test_deleting_an_issue_with_children_is_refused(
    session: Session,
    project: Project,
) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    make(session, project, IssueType.STORY, "Story", parent_id=epic)

    with pytest.raises(IssueHasChildrenError) as caught:
        issue_service.delete_issue(session, epic)
    assert caught.value.code == "issue.has_children"


def test_deleting_a_childless_issue_succeeds(
    session: Session,
    project: Project,
) -> None:
    issue_id = make(session, project)
    issue_service.delete_issue(session, issue_id)

    with pytest.raises(NotFoundError):
        issue_service.get_issue(session, issue_id)


def test_a_user_named_on_an_issue_cannot_be_deleted(
    session: Session,
    project: Project,
) -> None:
    user = user_service.create_user(session, "Ada")
    make(session, project, reporter_id=user.id)

    with pytest.raises(UserInUseError) as caught:
        user_service.delete_user(session, user.id)
    assert caught.value.code == "user.in_use"


def test_an_unreferenced_user_can_still_be_deleted(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    user_service.delete_user(session, user.id)

    with pytest.raises(NotFoundError):
        user_service.get_user(session, user.id)


def test_effort_is_stored_as_minutes(session: Session, project: Project) -> None:
    issue = issue_service.get_issue(
        session,
        make(session, project, estimate_minutes=90),
    )
    assert issue.estimate_minutes == 90
    assert issue.remaining_minutes == 90

    updated = issue_service.update_issue(
        session,
        issue.id,
        remaining_minutes=45,
        estimate_minutes=120,
    )
    assert updated.estimate_minutes == 120
    assert updated.remaining_minutes == 45

    cleared = issue_service.update_issue(session, issue.id, estimate_minutes=None)
    assert cleared.estimate_minutes is None
    assert cleared.remaining_minutes == 45


def test_remaining_stays_unset_when_there_is_no_estimate(
    session: Session,
    project: Project,
) -> None:
    issue = issue_service.get_issue(session, make(session, project))
    assert issue.estimate_minutes is None
    assert issue.remaining_minutes is None


def test_negative_effort_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(InvalidIssueError):
        make(session, project, estimate_minutes=-1)


def test_rollup_covers_the_issue_and_its_descendants(
    session: Session,
    project: Project,
) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic", estimate_minutes=120)
    story = make(
        session,
        project,
        IssueType.STORY,
        "Story",
        parent_id=epic,
        estimate_minutes=60,
        remaining_minutes=30,
    )
    make(
        session,
        project,
        IssueType.SUBTASK,
        "Done",
        parent_id=story,
        estimate_minutes=30,
        remaining_minutes=0,
    )
    issue_service.update_issue(
        session,
        issue_service.list_children(session, story)[0].id,
        status=IssueStatus.DONE,
    )

    rollup = issue_service.issue_rollup(session, epic)
    assert rollup.estimate_minutes == 210
    assert rollup.remaining_minutes == 150
    assert rollup.descendants == 2
    assert rollup.descendants_done == 1
    assert rollup.descendants_cancelled == 0
    own = issue_service.get_issue(session, epic)
    assert own.estimate_minutes == 120


def test_filters_narrow_the_list(session: Session, project: Project) -> None:
    epic = make(session, project, IssueType.EPIC, "Epic")
    story = make(session, project, IssueType.STORY, "Story", parent_id=epic)
    issue_service.update_issue(session, story, status=IssueStatus.DONE)

    by_type = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(type=IssueType.STORY),
    )
    by_status = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(status=IssueStatus.DONE),
    )
    by_parent = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(parent_id=epic),
    )

    assert [i.id for i in by_type] == [story]
    assert [i.id for i in by_status] == [story]
    assert [i.id for i in by_parent] == [story]


def test_assignee_filters_narrow_the_list(session: Session, project: Project) -> None:
    ada = user_service.create_user(session, "Ada")
    assigned = make(session, project, title="Assigned", assignee_id=ada.id)
    open_id = make(session, project, title="Open")

    by_person = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(assignee_id=ada.id),
    )
    unassigned = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(unassigned=True),
    )

    assert [i.id for i in by_person] == [assigned]
    assert [i.id for i in unassigned] == [open_id]


def test_label_filters_narrow_the_list(session: Session, project: Project) -> None:
    tagged = make(session, project, title="Tagged", labels=["urgent"])
    bare = make(session, project, title="Bare")

    by_name = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(label="urgent"),
    )
    unlabeled = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(unlabeled=True),
    )

    assert [i.id for i in by_name] == [tagged]
    assert [i.id for i in unlabeled] == [bare]


def test_counts_cover_every_status(session: Session, project: Project) -> None:
    make(session, project)
    counts = issue_service.count_by_status(session, project.id)

    assert counts[IssueStatus.TODO] == 1
    assert counts[IssueStatus.DONE] == 0
    assert counts[IssueStatus.CANCELLED] == 0
    assert len(counts) == len(IssueStatus)


def test_deleting_a_project_takes_its_issues(
    session: Session,
    project: Project,
) -> None:
    issue_id = make(session, project)
    project_service.delete_project(session, project.id)
    session.expire_all()

    with pytest.raises(NotFoundError):
        issue_service.get_issue(session, issue_id)


def test_a_due_date_round_trips(session: Session, project: Project) -> None:
    due = datetime(2026, 9, 15, 17, 0)
    issue = issue_service.get_issue(
        session,
        make(session, project, due_at=due),
    )
    assert issue.due_at == due

    cleared = issue_service.update_issue(session, issue.id, due_at=None)
    assert cleared.due_at is None


def test_a_start_date_round_trips(session: Session, project: Project) -> None:
    start = datetime(2026, 9, 14, 9, 0)
    issue = issue_service.get_issue(
        session,
        make(session, project, start_at=start),
    )
    assert issue.start_at == start

    cleared = issue_service.update_issue(session, issue.id, start_at=None)
    assert cleared.start_at is None


def test_start_after_due_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(InvalidIssueError, match="Start cannot be after due"):
        make(
            session,
            project,
            start_at=datetime(2026, 9, 16, 9, 0),
            due_at=datetime(2026, 9, 15, 17, 0),
        )


def test_updating_start_after_due_is_refused(
    session: Session,
    project: Project,
) -> None:
    issue_id = make(session, project, due_at=datetime(2026, 9, 15, 17, 0))
    with pytest.raises(InvalidIssueError, match="Start cannot be after due"):
        issue_service.update_issue(
            session,
            issue_id,
            start_at=datetime(2026, 9, 16, 9, 0),
        )


def test_created_at_is_set_on_insert(session: Session, project: Project) -> None:
    issue = issue_service.get_issue(session, make(session, project))
    assert issue.created_at is not None
    assert issue.updated_at is not None


def test_a_malformed_due_date_is_refused() -> None:
    with pytest.raises(InvalidIssueError):
        issue_service.parse_due_at("next tuesday")


def test_a_blank_due_date_is_absent() -> None:
    assert issue_service.parse_due_at("  ") is None


def test_a_due_date_with_a_timezone_is_stored_naive_utc() -> None:
    parsed = issue_service.parse_due_at("2026-09-15T13:00:00-04:00")
    assert parsed == datetime(2026, 9, 15, 17, 0)
    assert parsed.tzinfo is None
