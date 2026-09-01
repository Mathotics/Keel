import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import IssueStatus, IssueType
from keel.services import boards as board_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _issue(
    session: Session,
    project: Project,
    title: str,
    type: IssueType = IssueType.STORY,
    status: IssueStatus = IssueStatus.TODO,
    assignee_id: int | None = None,
) -> None:
    issue = issue_service.create_issue(
        session,
        project.id,
        type=type,
        title=title,
        assignee_id=assignee_id,
    )
    if status is not IssueStatus.TODO:
        issue_service.update_issue(session, issue.id, status=status)


def test_every_status_has_a_column_even_when_empty(
    session: Session,
    project: Project,
) -> None:
    board = board_service.project_board(session, project.id)

    assert [column.status for column in board.columns] == list(IssueStatus)
    assert all(column.cards == () for column in board.columns)


def test_issues_are_grouped_by_status(session: Session, project: Project) -> None:
    _issue(session, project, "Ready")
    _issue(session, project, "Finished", status=IssueStatus.DONE)

    board = board_service.project_board(session, project.id)
    by_status = {column.status: column.cards for column in board.columns}

    assert [card.issue.title for card in by_status[IssueStatus.TODO]] == ["Ready"]
    assert [card.issue.title for card in by_status[IssueStatus.DONE]] == ["Finished"]
    assert by_status[IssueStatus.IN_PROGRESS] == ()


def test_the_type_filter_is_applied_before_grouping(
    session: Session,
    project: Project,
) -> None:
    _issue(session, project, "Epic", type=IssueType.EPIC)
    _issue(session, project, "Story", type=IssueType.STORY)

    board = board_service.project_board(session, project.id, types=[IssueType.EPIC])
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["Epic"]


def test_a_full_type_filter_is_the_same_as_no_filter(
    session: Session,
    project: Project,
) -> None:
    _issue(session, project, "Epic", type=IssueType.EPIC)
    _issue(session, project, "Story", type=IssueType.STORY)

    filtered = board_service.project_board(session, project.id, types=list(IssueType))
    unfiltered = board_service.project_board(session, project.id)

    assert [card.issue.id for column in filtered.columns for card in column.cards] == [
        card.issue.id for column in unfiltered.columns for card in column.cards
    ]


def test_cards_carry_the_readable_key_and_assignee(
    session: Session,
    project: Project,
) -> None:
    ada = user_service.create_user(session, "Ada")
    _issue(session, project, "Assigned", assignee_id=ada.id)
    _issue(session, project, "Open")

    cards = board_service.project_board(session, project.id).columns[0].cards

    assert cards[0].key == "KEEL-1"
    assert cards[0].assignee_name == "Ada"
    assert cards[1].assignee_name is None
