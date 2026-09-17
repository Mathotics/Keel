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
    parent_id: int | None = None,
) -> None:
    issue = issue_service.create_issue(
        session,
        project.id,
        type=type,
        title=title,
        assignee_id=assignee_id,
        sprint_id=sprint_id,
        parent_id=parent_id,
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
    _issue(session, project, "Dropped", status=IssueStatus.CANCELLED)

    board = board_service.project_board(session, project.id)
    by_status = {column.status: column.cards for column in board.columns}

    assert [card.issue.title for card in by_status[IssueStatus.TODO]] == ["Ready"]
    assert [card.issue.title for card in by_status[IssueStatus.DONE]] == ["Finished"]
    assert [card.issue.title for card in by_status[IssueStatus.CANCELLED]] == [
        "Dropped"
    ]
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
    assert cards[0].parent_key is None
    assert cards[1].assignee_name is None
    assert cards[1].parent_key is None


def test_cards_carry_a_parent_key_when_the_issue_has_a_parent(
    session: Session,
    project: Project,
) -> None:
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="Epic",
    )
    story = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Story",
        parent_id=epic.id,
    )
    issue_service.create_issue(
        session,
        project.id,
        type=IssueType.SUBTASK,
        title="Subtask",
        parent_id=story.id,
    )

    cards = {
        card.issue.title: card
        for card in board_service.project_board(session, project.id).columns[0].cards
    }

    assert cards["Epic"].parent_key is None
    assert cards["Story"].parent_key == "KEEL-1"
    assert cards["Subtask"].parent_key == "KEEL-2"


def test_a_type_filter_still_resolves_a_hidden_parent_key(
    session: Session,
    project: Project,
) -> None:
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="Epic",
    )
    _issue(session, project, "Story", parent_id=epic.id)

    board = board_service.project_board(session, project.id, types=[IssueType.STORY])
    cards = [card for column in board.columns for card in column.cards]

    assert [card.issue.title for card in cards] == ["Story"]
    assert cards[0].parent_key == "KEEL-1"


def test_an_assignee_filter_still_resolves_an_assigned_parent(
    session: Session,
    project: Project,
) -> None:
    ada = user_service.create_user(session, "Ada")
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="Epic",
        assignee_id=ada.id,
    )
    _issue(session, project, "Story", parent_id=epic.id)

    board = board_service.project_board(session, project.id, unassigned=True)
    cards = [card for column in board.columns for card in column.cards]

    assert [card.issue.title for card in cards] == ["Story"]
    assert cards[0].parent_key == "KEEL-1"


def test_a_sprint_filter_still_resolves_a_parent_in_another_sprint(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="Epic",
        sprint_id=sprint.id,
    )
    _issue(session, project, "Story", parent_id=epic.id)

    board = board_service.project_board(session, project.id, unscheduled=True)
    cards = [card for column in board.columns for card in column.cards]

    assert [card.issue.title for card in cards] == ["Story"]
    assert cards[0].parent_key == "KEEL-1"


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, (None, False)),
        ("", (None, False)),
        ("  ", (None, False)),
        ("unlabeled", (None, True)),
        ("Urgent", ("urgent", False)),
    ],
)
def test_parse_label_filter_accepts_the_board_query_values(
    raw: str | None,
    expected: tuple[str | None, bool],
) -> None:
    assert board_service.parse_label_filter(raw) == expected


def test_parse_label_filter_rejects_an_illegal_name() -> None:
    with pytest.raises(InvalidIssueError):
        board_service.parse_label_filter("!!!")


def test_the_label_filter_is_applied_before_grouping(
    session: Session,
    project: Project,
) -> None:
    tagged = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Tagged",
        labels=["urgent"],
    )
    issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Bare",
    )
    board = board_service.project_board(session, project.id, label="urgent")
    cards = [card for column in board.columns for card in column.cards]
    assert [card.issue.id for card in cards] == [tagged.id]
    assert cards[0].labels == ("urgent",)


def test_the_unlabeled_filter_keeps_only_bare_cards(
    session: Session,
    project: Project,
) -> None:
    issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Tagged",
        labels=["urgent"],
    )
    bare = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Bare",
    )
    board = board_service.project_board(session, project.id, unlabeled=True)
    cards = [card for column in board.columns for card in column.cards]
    assert [card.issue.id for card in cards] == [bare.id]


def test_parse_board_grouping_accepts_sprint_or_nothing() -> None:
    assert board_service.parse_board_grouping(None) is None
    assert board_service.parse_board_grouping("") is None
    assert board_service.parse_board_grouping("sprint") == "sprint"


def test_parse_board_grouping_rejects_an_unknown_value() -> None:
    with pytest.raises(InvalidIssueError):
        board_service.parse_board_grouping("assignee")


def _titles(board: board_service.Board) -> list[str]:
    return [card.issue.title for column in board.columns for card in column.cards]


def test_the_master_board_mixes_projects(
    session: Session,
    project: Project,
) -> None:
    house = project_service.create_project(session, "HOUSE", "House")
    _issue(session, project, "Keel work")
    _issue(session, house, "House work")

    board = board_service.master_board(session)
    assert board.project is None
    assert _titles(board) == ["House work", "Keel work"]
    keys = [card.key for column in board.columns for card in column.cards]
    assert keys == ["HOUSE-1", "KEEL-1"]


def test_the_master_board_hides_closed_work_in_completed_sprints(
    session: Session,
    project: Project,
) -> None:
    past = sprint_service.create_sprint(session, project.id, "Past")
    _issue(
        session,
        project,
        "Finished past",
        status=IssueStatus.DONE,
        sprint_id=past.id,
    )
    _issue(
        session,
        project,
        "Dropped past",
        status=IssueStatus.CANCELLED,
        sprint_id=past.id,
    )
    _issue(session, project, "Unscheduled done", status=IssueStatus.DONE)
    sprint_service.start_sprint(session, past.id)
    sprint_service.complete_sprint(session, past.id)
    current = sprint_service.create_sprint(session, project.id, "Now")
    _issue(session, project, "Done now", status=IssueStatus.DONE, sprint_id=current.id)
    sprint_service.start_sprint(session, current.id)

    master = board_service.master_board(session)
    project_view = board_service.project_board(session, project.id)

    assert "Finished past" not in _titles(master)
    assert "Dropped past" not in _titles(master)
    assert "Unscheduled done" in _titles(master)
    assert "Done now" in _titles(master)
    assert "Finished past" in _titles(project_view)
    assert "Dropped past" in _titles(project_view)


def test_the_master_board_project_filter_keeps_one_project(
    session: Session,
    project: Project,
) -> None:
    house = project_service.create_project(session, "HOUSE", "House")
    _issue(session, project, "Keel work")
    _issue(session, house, "House work")

    board = board_service.master_board(session, project_id=house.id)
    assert _titles(board) == ["House work"]


def test_master_lanes_prefix_sprint_names_with_the_project_key(
    session: Session,
    project: Project,
) -> None:
    house = project_service.create_project(session, "HOUSE", "House")
    keel_sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    house_sprint = sprint_service.create_sprint(session, house.id, "Sprint 1")
    _issue(session, project, "Keel card", sprint_id=keel_sprint.id)
    _issue(session, house, "House card", sprint_id=house_sprint.id)

    board = board_service.master_board(session)
    assert [lane.name for lane in board.lanes] == [
        "HOUSE / Sprint 1",
        "KEEL / Sprint 1",
        "Unscheduled",
    ]


def test_parse_project_filter_accepts_empty_or_a_key() -> None:
    assert board_service.parse_project_filter(None) is None
    assert board_service.parse_project_filter("") is None
    assert board_service.parse_project_filter("  KEEL ") == "KEEL"
