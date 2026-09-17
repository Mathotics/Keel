import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import IssueType
from keel.domain.errors import InvalidIssueError, NotFoundError
from keel.services import history as history_service
from keel.services import issues as issue_service
from keel.services import labels as label_service
from keel.services import projects as project_service


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _story(session: Session, project: Project, **kwargs: object) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Something",
        **kwargs,  # type: ignore[arg-type]
    ).id


def test_create_can_attach_labels(session: Session, project: Project) -> None:
    issue_id = _story(session, project, labels="Urgent, bug")
    assert label_service.names_for_issue(session, issue_id) == ["bug", "urgent"]
    assert list(history_service.list_history(session, issue_id)) == []


def test_adding_a_label_records_history(session: Session, project: Project) -> None:
    issue_id = _story(session, project)
    label_service.add_issue_label(session, issue_id, "Urgent", actor_name="Ada")

    events = history_service.list_history(session, issue_id)
    assert len(events) == 1
    assert events[0].field == "labels"
    assert events[0].from_value == "none"
    assert events[0].to_value == "urgent"
    assert events[0].actor_name == "Ada"


def test_a_duplicate_add_does_not_append_history(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project, labels=["urgent"])
    label_service.add_issue_label(session, issue_id, "URGENT", actor_name="Ada")
    assert list(history_service.list_history(session, issue_id)) == []


def test_replacing_labels_clears_them(session: Session, project: Project) -> None:
    issue_id = _story(session, project, labels=["bug", "urgent"])
    issue_service.update_issue(session, issue_id, labels=(), actor_name="Ada")
    assert label_service.names_for_issue(session, issue_id) == []
    event = history_service.list_history(session, issue_id)[0]
    assert event.from_value == "bug, urgent"
    assert event.to_value == "none"


def test_removing_a_label_keeps_the_others(session: Session, project: Project) -> None:
    issue_id = _story(session, project, labels=["bug", "urgent"])
    catalog = {label.name: label.id for label in label_service.list_labels(session)}
    label_service.remove_issue_label(
        session,
        issue_id,
        catalog["bug"],
        actor_name="Ada",
    )
    assert label_service.names_for_issue(session, issue_id) == ["urgent"]


def test_the_catalog_is_shared_across_projects(
    session: Session, project: Project
) -> None:
    other = project_service.create_project(session, "SITE", "Site")
    _story(session, project, labels=["urgent"])
    _story(session, other, labels=["urgent"])
    names = [label.name for label in label_service.list_labels(session)]
    assert names == ["urgent"]


def test_an_unknown_issue_is_refused(session: Session) -> None:
    with pytest.raises(NotFoundError):
        label_service.set_issue_labels(session, 999, ["urgent"])


def test_an_illegal_name_is_refused(session: Session, project: Project) -> None:
    issue_id = _story(session, project)
    with pytest.raises(InvalidIssueError):
        label_service.add_issue_label(session, issue_id, "!!!")
