from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Comment
from keel.domain.errors import InvalidCommentError, NotFoundError
from keel.services import issues as issue_service
from keel.services import users as user_service


def get_comment(session: Session, comment_id: int) -> Comment:
    comment = session.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError(f"No comment with id {comment_id}.")
    return comment


def list_comments(session: Session, issue_id: int) -> Sequence[Comment]:
    issue_service.get_issue(session, issue_id)
    return session.scalars(
        select(Comment)
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at, Comment.id),
    ).all()


def create_comment(
    session: Session,
    issue_id: int,
    body: str,
    author_id: int | None = None,
) -> Comment:
    issue = issue_service.get_issue(session, issue_id)
    if author_id is not None:
        user_service.get_user(session, author_id)
    comment = Comment(
        issue_id=issue.id,
        author_id=author_id,
        body=_clean_body(body),
    )
    session.add(comment)
    session.flush()
    return comment


def delete_comment(session: Session, comment_id: int) -> None:
    session.delete(get_comment(session, comment_id))
    session.flush()


def _clean_body(body: str) -> str:
    cleaned = body.strip()
    if not cleaned:
        raise InvalidCommentError("A comment needs a body.")
    return cleaned
