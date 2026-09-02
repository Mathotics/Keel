from fastapi import APIRouter, status

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.schemas.comment import CommentCreate, CommentRead
from keel.services import comments as comment_service

router = APIRouter(tags=["comments"])


@router.get("/issues/{issue_id}/comments", response_model=list[CommentRead])
def list_comments(issue_id: int, session: SessionDep) -> list[CommentRead]:
    return [
        CommentRead.of(comment)
        for comment in comment_service.list_comments(session, issue_id)
    ]


@router.post(
    "/issues/{issue_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    issue_id: int,
    payload: CommentCreate,
    session: SessionDep,
    acting_user: ActingUserDep,
) -> CommentRead:
    return CommentRead.of(
        comment_service.create_comment(
            session,
            issue_id,
            payload.body,
            author_id=None if acting_user is None else acting_user.id,
        ),
    )


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(comment_id: int, session: SessionDep) -> None:
    comment_service.delete_comment(session, comment_id)
