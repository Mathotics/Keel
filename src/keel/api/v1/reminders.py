from datetime import datetime

from fastapi import APIRouter, Depends, Response, status

from keel.api.v1.deps import SessionDep
from keel.api.v1.guards import AccessDep, require_issue, require_series
from keel.domain.access import Permission
from keel.schemas.reminder import (
    BundleRead,
    EffectiveRead,
    FireRead,
    RuleRead,
    RuleSlot,
    RuleWrite,
    SnoozeWrite,
    StateRead,
    StateWrite,
)
from keel.services import issues as issue_service
from keel.services import reminders as reminder_service

router = APIRouter(tags=["reminders"])


@router.get("/reminders", response_model=BundleRead)
def read_bundle(session: SessionDep, access: AccessDep) -> BundleRead:
    return reminder_service.bundle(session, _user(access))


@router.get("/reminders/schedule", response_model=list[FireRead])
def read_schedule(
    session: SessionDep,
    access: AccessDep,
    catch_up: bool = True,
) -> list[FireRead]:
    return reminder_service.schedule(
        session,
        access,
        _user(access),
        catch_up=catch_up,
    )


@router.get("/profile/reminders", response_model=RuleSlot)
def read_default(session: SessionDep, access: AccessDep) -> RuleSlot:
    return RuleSlot(rule=reminder_service.get_default(session, _user(access)))


@router.put("/profile/reminders", response_model=RuleRead)
def write_default(
    payload: RuleWrite,
    session: SessionDep,
    access: AccessDep,
) -> RuleRead:
    return reminder_service.save_default(session, _user(access), payload)


@router.get(
    "/series/{series_id}/reminder",
    response_model=RuleSlot,
    dependencies=[Depends(require_series(Permission.VIEW_SCHEDULES))],
)
def read_series_rule(
    series_id: int,
    session: SessionDep,
    access: AccessDep,
) -> RuleSlot:
    return RuleSlot(
        rule=reminder_service.get_series_rule(session, _user(access), series_id)
    )


@router.put(
    "/series/{series_id}/reminder",
    response_model=RuleRead,
    dependencies=[Depends(require_series(Permission.VIEW_SCHEDULES))],
)
def write_series_rule(
    series_id: int,
    payload: RuleWrite,
    session: SessionDep,
    access: AccessDep,
) -> RuleRead:
    return reminder_service.save_series_rule(
        session,
        _user(access),
        series_id,
        payload,
    )


@router.delete(
    "/series/{series_id}/reminder",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_series(Permission.VIEW_SCHEDULES))],
)
def remove_series_rule(
    series_id: int,
    session: SessionDep,
    access: AccessDep,
    base_updated_at: datetime | None = None,
) -> Response:
    reminder_service.delete_series_rule(
        session,
        _user(access),
        series_id,
        base_updated_at,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/issues/{issue_id}/reminder",
    response_model=EffectiveRead,
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def read_issue_rule(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
) -> EffectiveRead:
    issue = issue_service.get_issue(session, issue_id)
    return reminder_service.effective_issue(session, _user(access), issue)


@router.put(
    "/issues/{issue_id}/reminder",
    response_model=RuleRead,
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def write_issue_rule(
    issue_id: int,
    payload: RuleWrite,
    session: SessionDep,
    access: AccessDep,
) -> RuleRead:
    return reminder_service.save_issue_rule(session, _user(access), issue_id, payload)


@router.delete(
    "/issues/{issue_id}/reminder",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def remove_issue_rule(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
    base_updated_at: datetime | None = None,
) -> Response:
    reminder_service.delete_issue_rule(
        session,
        _user(access),
        issue_id,
        base_updated_at,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/issues/{issue_id}/reminder/snooze",
    response_model=StateRead,
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def snooze_issue(
    issue_id: int,
    payload: SnoozeWrite,
    session: SessionDep,
    access: AccessDep,
) -> StateRead:
    return reminder_service.snooze(
        session,
        _user(access),
        issue_id,
        payload.until,
        payload.base_updated_at,
    )


@router.post(
    "/issues/{issue_id}/reminder/dismiss-overdue",
    response_model=StateRead,
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def dismiss_issue(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
    payload: StateWrite | None = None,
) -> StateRead:
    base = None if payload is None else payload.base_updated_at
    return reminder_service.dismiss_overdue(session, _user(access), issue_id, base)


@router.post(
    "/issues/{issue_id}/reminder/resume-overdue",
    response_model=StateRead,
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def resume_issue(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
    payload: StateWrite | None = None,
) -> StateRead:
    base = None if payload is None else payload.base_updated_at
    return reminder_service.resume_overdue(session, _user(access), issue_id, base)


def _user(access: AccessDep) -> int:
    assert access.user_id is not None
    return access.user_id
