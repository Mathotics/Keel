from fastapi import APIRouter, Response, status

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.db.models import Notice
from keel.domain.enums import NotificationType
from keel.domain.errors import NotFoundError
from keel.schemas.notification import NoticeRead, PreferenceRead, PreferenceReplace
from keel.services import notifications as notification_service
from keel.services.notifications import PreferenceChoice

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _user(acting: ActingUserDep) -> int:
    if acting is None:
        raise NotFoundError("Sign in.")
    return acting.id


def _notice(notice: Notice) -> NoticeRead:
    return NoticeRead(
        id=notice.id,
        type=NotificationType(notice.notice_type),
        actor_id=notice.actor_id,
        actor_name=notice.actor_name,
        issue_id=notice.issue_id,
        issue_key=notice.issue_key,
        issue_title=notice.issue_title,
        body=notice.body,
        read_at=notice.read_at,
        created_at=notice.created_at,
        deliver_at=notice.deliver_at,
    )


def _preference(choice: PreferenceChoice) -> PreferenceRead:
    return PreferenceRead(
        type=choice.type,
        email=choice.email,
        phone=choice.phone,
        bell=choice.bell,
    )


@router.get("", response_model=list[NoticeRead])
def list_notifications(session: SessionDep, acting: ActingUserDep) -> list[NoticeRead]:
    notices = notification_service.list_notices(session, _user(acting))
    return [_notice(notice) for notice in notices]


@router.get("/preferences", response_model=list[PreferenceRead])
def read_preferences(
    session: SessionDep,
    acting: ActingUserDep,
) -> list[PreferenceRead]:
    choices = notification_service.effective_preferences(session, _user(acting))
    return [_preference(choice) for choice in choices]


@router.put("/preferences", response_model=list[PreferenceRead])
def replace_preferences(
    payload: PreferenceReplace,
    session: SessionDep,
    acting: ActingUserDep,
) -> list[PreferenceRead]:
    choices = notification_service.replace_preferences(
        session,
        _user(acting),
        [
            PreferenceChoice(
                type=item.type,
                email=item.email,
                phone=item.phone,
                bell=item.bell,
            )
            for item in payload.preferences
        ],
    )
    return [_preference(choice) for choice in choices]


@router.post("/{notice_id}/read", response_model=NoticeRead)
def mark_notification_read(
    notice_id: int,
    session: SessionDep,
    acting: ActingUserDep,
) -> NoticeRead:
    notice = notification_service.mark_read(session, _user(acting), notice_id)
    return _notice(notice)


@router.delete("/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notice_id: int,
    session: SessionDep,
    acting: ActingUserDep,
) -> Response:
    notification_service.delete_notice(session, _user(acting), notice_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
