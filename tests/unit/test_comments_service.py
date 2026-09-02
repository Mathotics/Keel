import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import IssueType
from keel.domain.errors import InvalidCommentError, NotFoundError, UserInUseError
from keel.services import comments as comment_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _issue(session: Session, project: Project) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Something",
    ).id


def test_comments_are_listed_oldest_first(session: Session, project: Project) -> None:
    issue_id = _issue(session, project)
    first = comment_service.create_comment(session, issue_id, "First")
    second = comment_service.create_comment(session, issue_id, "Second")

    listed = comment_service.list_comments(session, issue_id)
    assert [comment.id for comment in listed] == [first.id, second.id]
    assert [comment.body for comment in listed] == ["First", "Second"]


def test_a_blank_comment_is_refused(session: Session, project: Project) -> None:
    issue_id = _issue(session, project)
    with pytest.raises(InvalidCommentError) as caught:
        comment_service.create_comment(session, issue_id, "   ")
    assert caught.value.code == "comment.invalid"


def test_a_comment_can_be_removed(session: Session, project: Project) -> None:
    issue_id = _issue(session, project)
    comment = comment_service.create_comment(session, issue_id, "Note")
    comment_service.delete_comment(session, comment.id)
    assert list(comment_service.list_comments(session, issue_id)) == []


def test_deleting_an_issue_cascades_its_comments(
    session: Session,
    project: Project,
) -> None:
    issue_id = _issue(session, project)
    comment = comment_service.create_comment(session, issue_id, "Note")
    comment_id = comment.id
    issue_service.delete_issue(session, issue_id)
    session.expire_all()
    with pytest.raises(NotFoundError):
        comment_service.get_comment(session, comment_id)


def test_a_comment_author_cannot_be_deleted(session: Session, project: Project) -> None:
    ada = user_service.create_user(session, "Ada")
    issue_id = _issue(session, project)
    comment_service.create_comment(session, issue_id, "Note", author_id=ada.id)

    with pytest.raises(UserInUseError) as caught:
        user_service.delete_user(session, ada.id)
    assert caught.value.code == "user.in_use"
    assert caught.value.context["comments"] == 1
    assert caught.value.context["issues"] == 0
