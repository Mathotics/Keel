from datetime import datetime

from fastapi import APIRouter, Response, status

from keel.api.v1.deps import SessionDep
from keel.api.v1.guards import AccessDep, guard_issue, guard_series
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


@router.get("/series/{series_id}/reminder", response_model=RuleSlot)
def read_series_rule(
    series_id: int,
    session: SessionDep,
    access: AccessDep,
) -> RuleSlot:
    guard_series(session, access, series_id, Permission.VIEW_SCHEDULES)
    return RuleSlot(
        rule=reminder_service.get_series_rule(session, _user(access), series_id)
    )


@router.put("/series/{series_id}/reminder", response_model=RuleRead)
def write_series_rule(
    series_id: int,
    payload: RuleWrite,
    session: SessionDep,
    access: AccessDep,
) -> RuleRead:
    guard_series(session, access, series_id, Permission.VIEW_SCHEDULES)
    return reminder_service.save_series_rule(
        session,
        _user(access),
        series_id,
        payload,
    )


@router.delete("/series/{series_id}/reminder", status_code=status.HTTP_204_NO_CONTENT)
def remove_series_rule(
    series_id: int,
    session: SessionDep,
    access: AccessDep,
    base_updated_at: datetime | None = None,
) -> Response:
    guard_series(session, access, series_id, Permission.VIEW_SCHEDULES)
    reminder_service.delete_series_rule(
        session,
        _user(access),
        series_id,
        base_updated_at,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/issues/{issue_id}/reminder", response_model=EffectiveRead)
def read_issue_rule(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
) -> EffectiveRead:
    guard_issue(session, access, issue_id, Permission.VIEW_ISSUES)
    issue = issue_service.get_issue(session, issue_id)
    return reminder_service.effective_issue(session, _user(access), issue)


@router.put("/issues/{issue_id}/reminder", response_model=RuleRead)
def write_issue_rule(
    issue_id: int,
    payload: RuleWrite,
    session: SessionDep,
    access: AccessDep,
) -> RuleRead:
    guard_issue(session, access, issue_id, Permission.VIEW_ISSUES)
    return reminder_service.save_issue_rule(session, _user(access), issue_id, payload)


@router.delete("/issues/{issue_id}/reminder", status_code=status.HTTP_204_NO_CONTENT)
def remove_issue_rule(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
    base_updated_at: datetime | None = None,
) -> Response:
    guard_issue(session, access, issue_id, Permission.VIEW_ISSUES)
    reminder_service.delete_issue_rule(
        session,
        _user(access),
        issue_id,
        base_updated_at,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/issues/{issue_id}/reminder/snooze", response_model=StateRead)
def snooze_issue(
    issue_id: int,
    payload: SnoozeWrite,
    session: SessionDep,
    access: AccessDep,
) -> StateRead:
    guard_issue(session, access, issue_id, Permission.VIEW_ISSUES)
    return reminder_service.snooze(
        session,
        _user(access),
        issue_id,
        payload.until,
        payload.base_updated_at,
    )


@router.post("/issues/{issue_id}/reminder/dismiss-overdue", response_model=StateRead)
def dismiss_issue(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
    payload: StateWrite | None = None,
) -> StateRead:
    guard_issue(session, access, issue_id, Permission.VIEW_ISSUES)
    base = None if payload is None else payload.base_updated_at
    return reminder_service.dismiss_overdue(session, _user(access), issue_id, base)


@router.post("/issues/{issue_id}/reminder/resume-overdue", response_model=StateRead)
def resume_issue(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
    payload: StateWrite | None = None,
) -> StateRead:
    guard_issue(session, access, issue_id, Permission.VIEW_ISSUES)
    base = None if payload is None else payload.base_updated_at
    return reminder_service.resume_overdue(session, _user(access), issue_id, base)


def _user(access: AccessDep) -> int:
    assert access.user_id is not None
    return access.user_id
