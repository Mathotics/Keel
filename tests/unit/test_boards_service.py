import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import DependencyKind, IssueStatus, IssueType
from keel.domain.errors import InvalidIssueError
from keel.services import boards as board_service
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
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
    sprint_id: int | None = None,
) -> None:
    issue = issue_service.create_issue(
        session,
        project.id,
        type=type,
        title=title,
        assignee_id=assignee_id,
        sprint_id=sprint_id,
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


def test_the_assignee_filter_is_applied_before_grouping(
    session: Session,
    project: Project,
) -> None:
    ada = user_service.create_user(session, "Ada")
    _issue(session, project, "Ada's", assignee_id=ada.id)
    _issue(session, project, "Open")

    board = board_service.project_board(session, project.id, assignee_id=ada.id)
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["Ada's"]


def test_the_unassigned_filter_keeps_only_open_cards(
    session: Session,
    project: Project,
) -> None:
    ada = user_service.create_user(session, "Ada")
    _issue(session, project, "Ada's", assignee_id=ada.id)
    _issue(session, project, "Open")

    board = board_service.project_board(session, project.id, unassigned=True)
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["Open"]


def test_type_and_assignee_filters_combine(
    session: Session,
    project: Project,
) -> None:
    ada = user_service.create_user(session, "Ada")
    _issue(session, project, "Ada epic", type=IssueType.EPIC, assignee_id=ada.id)
    _issue(session, project, "Ada story", type=IssueType.STORY, assignee_id=ada.id)
    _issue(session, project, "Open epic", type=IssueType.EPIC)

    board = board_service.project_board(
        session,
        project.id,
        types=[IssueType.EPIC],
        assignee_id=ada.id,
    )
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["Ada epic"]


def test_the_sprint_filter_is_applied_before_grouping(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    _issue(session, project, "In sprint", sprint_id=sprint.id)
    _issue(session, project, "Waiting")

    board = board_service.project_board(session, project.id, sprint_id=sprint.id)
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["In sprint"]


def test_the_unscheduled_filter_keeps_only_backlog_cards(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    _issue(session, project, "In sprint", sprint_id=sprint.id)
    _issue(session, project, "Waiting")

    board = board_service.project_board(session, project.id, unscheduled=True)
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["Waiting"]


def test_type_and_sprint_filters_combine(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    _issue(
        session,
        project,
        "Sprint epic",
        type=IssueType.EPIC,
        sprint_id=sprint.id,
    )
    _issue(
        session,
        project,
        "Sprint story",
        type=IssueType.STORY,
        sprint_id=sprint.id,
    )
    _issue(session, project, "Open epic", type=IssueType.EPIC)

    board = board_service.project_board(
        session,
        project.id,
        types=[IssueType.EPIC],
        sprint_id=sprint.id,
    )
    titles = [card.issue.title for column in board.columns for card in column.cards]

    assert titles == ["Sprint epic"]


def test_lanes_group_cards_by_sprint(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    _issue(session, project, "In sprint", sprint_id=sprint.id)
    _issue(session, project, "Waiting")

    board = board_service.project_board(session, project.id)

    assert [lane.name for lane in board.lanes] == ["Sprint 1", "Unscheduled"]
    assert [card.issue.title for card in board.lanes[0].columns[0].cards] == [
        "In sprint",
    ]
    assert [card.issue.title for card in board.lanes[1].columns[0].cards] == [
        "Waiting",
    ]


def test_a_completed_sprint_without_cards_is_not_a_lane(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Now")
    later = sprint_service.create_sprint(session, project.id, "Later")
    sprint_service.start_sprint(session, current.id)
    sprint_service.complete_sprint(session, current.id)

    board = board_service.project_board(session, project.id)
    assert [lane.name for lane in board.lanes] == [later.name, "Unscheduled"]


def test_the_sprint_filter_narrows_lanes(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    _issue(session, project, "In sprint", sprint_id=sprint.id)
    _issue(session, project, "Waiting")

    board = board_service.project_board(session, project.id, sprint_id=sprint.id)
    assert [lane.name for lane in board.lanes] == ["Sprint 1"]


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


def test_cards_carry_unresolved_blocker_counts(
    session: Session,
    project: Project,
) -> None:
    blocker = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Blocker",
    )
    waiting = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Waiting",
    )
    dependency_service.create_dependency(
        session,
        blocker.id,
        waiting.id,
        DependencyKind.BLOCKS,
    )

    cards = {
        card.issue.title: card
        for card in board_service.project_board(session, project.id).columns[0].cards
    }
    assert cards["Waiting"].unresolved_blockers == 1
    assert cards["Blocker"].unresolved_blockers == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, (None, False)),
        ("", (None, False)),
        ("  ", (None, False)),
        ("unassigned", (None, True)),
        ("12", (12, False)),
    ],
)
def test_parse_assignee_filter_accepts_the_board_query_values(
    raw: str | None,
    expected: tuple[int | None, bool],
) -> None:
    assert board_service.parse_assignee_filter(raw) == expected


def test_parse_assignee_filter_rejects_an_unknown_value() -> None:
    with pytest.raises(InvalidIssueError):
        board_service.parse_assignee_filter("Ada")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, (None, False)),
        ("", (None, False)),
        ("  ", (None, False)),
        ("unscheduled", (None, True)),
        ("12", (12, False)),
    ],
)
def test_parse_sprint_filter_accepts_the_board_query_values(
    raw: str | None,
    expected: tuple[int | None, bool],
) -> None:
    assert board_service.parse_sprint_filter(raw) == expected


def test_parse_sprint_filter_rejects_an_unknown_value() -> None:
    with pytest.raises(InvalidIssueError):
        board_service.parse_sprint_filter("Sprint 1")


def test_parse_board_grouping_accepts_sprint_or_nothing() -> None:
    assert board_service.parse_board_grouping(None) is None
    assert board_service.parse_board_grouping("") is None
    assert board_service.parse_board_grouping("sprint") == "sprint"


def test_parse_board_grouping_rejects_an_unknown_value() -> None:
    with pytest.raises(InvalidIssueError):
        board_service.parse_board_grouping("assignee")
