import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import IssueType
from keel.domain.errors import InvalidIssueError
from keel.services import issues as issue_service
from keel.services import lookup as lookup_service
from keel.services import projects as project_service
from keel.services import users as user_service


def _project(session: Session, key: str = "KEEL") -> Project:
    return project_service.create_project(session, key, key.title())


def _issue(session: Session, project: Project, title: str) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title=title,
    ).id


def test_issue_suggestions_match_key_and_title_only(session: Session) -> None:
    project = _project(session)
    other = _project(session, "HOME")
    first = _issue(session, project, "Take out trash")
    second = _issue(session, project, "Plumbing repair")
    _issue(session, other, "Take out recycling")
    described = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Quiet",
        description="trash day notes",
    )

    by_title = lookup_service.suggest_issues(session, "trash", project_id=project.id)
    assert [hit.id for hit in by_title] == [first]
    assert by_title[0].key == "KEEL-1"
    by_key = lookup_service.suggest_issues(session, "KEEL-2", project_id=project.id)
    assert [hit.id for hit in by_key] == [second]
    assert lookup_service.suggest_issues(session, "") == []
    assert lookup_service.suggest_issues(session, "trash day") == []
    skipped = lookup_service.suggest_issues(
        session,
        "trash",
        project_id=project.id,
        exclude_id=first,
    )
    assert skipped == []
    assert described.id not in [hit.id for hit in by_title]


def test_issue_suggestions_stop_at_ten(session: Session) -> None:
    project = _project(session)
    for number in range(12):
        _issue(session, project, f"Widget {number}")
    hits = lookup_service.suggest_issues(session, "widget", project_id=project.id)
    assert len(hits) == lookup_service.LIMIT
    assert hits[0].key == "KEEL-1"
    assert hits[-1].key == "KEEL-10"


def test_label_suggestions_keep_unlabeled_as_a_prefix(session: Session) -> None:
    project = _project(session)
    _issue(session, project, "Tagged")
    issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Tagged",
        labels="Plumbing, urgent",
    )
    assert lookup_service.suggest_labels(session, "") == ["unlabeled"]
    assert lookup_service.suggest_labels(session, "unl") == ["unlabeled"]
    assert lookup_service.suggest_labels(session, "plumb") == ["plumbing"]
    assert "unlabeled" not in lookup_service.suggest_labels(session, "urgent")


def test_a_posted_issue_accepts_an_id_a_key_or_a_copied_suggestion(
    session: Session,
) -> None:
    project = _project(session)
    home = _project(session, "HOME")
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="Parent",
    )
    home_issue = _issue(session, home, "Elsewhere")
    display = lookup_service.issue_display("KEEL-1", "Parent")

    assert (
        lookup_service.resolve_posted_issue(
            session,
            str(epic.id),
            "not a key",
            project_id=project.id,
            message=lookup_service.PARENT_MESSAGE,
        )
        == epic.id
    )
    assert (
        lookup_service.resolve_posted_issue(
            session,
            "",
            "KEEL-1",
            project_id=project.id,
            message=lookup_service.PARENT_MESSAGE,
        )
        == epic.id
    )
    assert (
        lookup_service.resolve_posted_issue(
            session,
            "",
            display,
            project_id=project.id,
            message=lookup_service.PARENT_MESSAGE,
        )
        == epic.id
    )
    assert (
        lookup_service.resolve_posted_issue(
            session,
            "",
            "",
            project_id=project.id,
            message=lookup_service.PARENT_MESSAGE,
        )
        is None
    )
    try:
        lookup_service.resolve_posted_issue(
            session,
            "",
            "Parent",
            project_id=project.id,
            message=lookup_service.PARENT_MESSAGE,
        )
    except InvalidIssueError as exc:
        assert exc.message == lookup_service.PARENT_MESSAGE
    else:
        raise AssertionError("a title alone must be refused")
    try:
        lookup_service.resolve_posted_issue(
            session,
            "",
            "HOME-1",
            project_id=project.id,
            message=lookup_service.PARENT_MESSAGE,
        )
    except InvalidIssueError as exc:
        assert exc.message == lookup_service.PARENT_MESSAGE
    else:
        raise AssertionError("a parent in another project must be refused")
    assert (
        lookup_service.resolve_posted_issue(
            session,
            "",
            "HOME-1",
            project_id=None,
            message=lookup_service.LINK_MESSAGE,
        )
        == home_issue
    )


def test_a_board_label_must_be_empty_unlabeled_or_a_catalog_name(
    session: Session,
) -> None:
    project = _project(session)
    issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Tagged",
        labels="urgent",
    )
    assert lookup_service.interpret_board_label(session, None) == (None, False, None)
    assert lookup_service.interpret_board_label(session, "  ") == (None, False, None)
    assert lookup_service.interpret_board_label(session, "unlabeled") == (
        None,
        True,
        None,
    )
    assert lookup_service.interpret_board_label(session, "Urgent") == (
        "urgent",
        False,
        None,
    )
    name, unlabeled, message = lookup_service.interpret_board_label(session, "nope")
    assert (name, unlabeled) == (None, False)
    assert message == lookup_service.LABEL_MESSAGE
    _name, _unlabeled, invalid = lookup_service.interpret_board_label(session, "!!!")
    assert invalid


def test_user_suggestions_match_name_and_keep_unassigned(session: Session) -> None:
    ada = user_service.create_user(session, "Ada Lovelace")
    user_service.create_user(session, "Grace Hopper")

    assert lookup_service.suggest_users(session, "") == [
        lookup_service.UserSuggestion(id=None, label="Unassigned"),
    ]
    matched = lookup_service.suggest_users(session, "love")
    assert matched == [
        lookup_service.UserSuggestion(id=ada.id, label="Ada Lovelace"),
    ]
    by_username = lookup_service.suggest_users(session, "grace hopper")
    assert [hit.label for hit in by_username] == ["Grace Hopper"]
    assert lookup_service.suggest_users(session, "un")[0].label == "Unassigned"
    assert lookup_service.resolve_posted_user(session, "", "Ada Lovelace") == ada.id
    assert lookup_service.resolve_posted_user(session, str(ada.id), "") == ada.id
    assert lookup_service.resolve_posted_user(session, "", "Unassigned") is None
    assert lookup_service.resolve_posted_user(session, "", "") is None
    with pytest.raises(InvalidIssueError):
        lookup_service.resolve_posted_user(session, "", "Nobody")

    assert lookup_service.interpret_board_assignee(session, None) == (
        None,
        False,
        "",
        None,
    )
    assert lookup_service.interpret_board_assignee(session, "unassigned") == (
        None,
        True,
        "Unassigned",
        None,
    )
    assert lookup_service.interpret_board_assignee(session, "ada lovelace") == (
        ada.id,
        False,
        "Ada Lovelace",
        None,
    )
    missing = lookup_service.interpret_board_assignee(session, "Nope")
    assert missing[3] == lookup_service.USER_MESSAGE
