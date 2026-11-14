from fastapi import APIRouter, Depends, status

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.api.v1.guards import require_comment_delete, require_issue
from keel.domain.access import Permission
from keel.schemas.comment import CommentCreate, CommentRead
from keel.services import comments as comment_service

router = APIRouter(tags=["comments"])


@router.get(
    "/issues/{issue_id}/comments",
    response_model=list[CommentRead],
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def list_comments(issue_id: int, session: SessionDep) -> list[CommentRead]:
    return [
        CommentRead.of(comment)
        for comment in comment_service.list_comments(session, issue_id)
    ]


@router.post(
    "/issues/{issue_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_issue(Permission.COMMENT_ISSUES))],
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


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_comment_delete)],
)
def delete_comment(comment_id: int, session: SessionDep) -> None:
    comment_service.delete_comment(session, comment_id)
