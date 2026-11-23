"""Reminder editors on the profile, an issue, and a series."""

from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from keel.domain.access import Permission
from keel.domain.errors import DomainError, NotFoundError
from keel.schemas.reminder import OffsetBody, RuleBody, RuleRead, RuleWrite
from keel.services import issues as issue_service
from keel.services import reminders as reminder_service
from keel.web.context import Chrome, ChromeDep, SessionDep
from keel.web.guards import require_issue, require_series

router = APIRouter()

_UNITS = ("minute", "hour", "day")


def profile_editor(session: Session, user_id: int) -> SimpleNamespace:
    rule = reminder_service.get_default(session, user_id)
    return _editor(
        rule,
        action="/web/profile/reminders",
        reset_action=None,
        note="Your default applies when an issue or series has no reminder of its own.",
        base=_stamp(None if rule is None else rule.updated_at),
    )


def series_editor(session: Session, user_id: int, series_id: int) -> SimpleNamespace:
    rule = reminder_service.get_series_rule(session, user_id, series_id)
    return _editor(
        rule,
        action=f"/web/schedules/{series_id}/reminder",
        reset_action=None
        if rule is None
        else f"/web/schedules/{series_id}/reminder/reset",
        note=(
            "This covers every issue the series spawns, until that issue "
            "has its own reminder."
        ),
        base=_stamp(None if rule is None else rule.updated_at),
        reset_label="Use your default",
    )


def issue_editor(session: Session, user_id: int, issue_id: int) -> SimpleNamespace:
    issue = issue_service.get_issue(session, issue_id)
    view = reminder_service.effective_issue(session, user_id, issue)
    notes = {
        "issue": "This issue has its own reminder.",
        "series": (
            "This follows the series reminder. Saving keeps a copy on this issue."
        ),
        "default": "This follows your default. Saving keeps a copy on this issue.",
        "none": "Nothing is set. Saving keeps a reminder on this issue.",
    }
    own = view.own
    return _editor(
        view.rule if own is None else own,
        action=f"/web/issues/{issue_id}/reminder",
        reset_action=None if own is None else f"/web/issues/{issue_id}/reminder/reset",
        note=notes[view.source],
        base=_stamp(None if own is None else own.updated_at),
        start_missing=view.start_missing,
        due_missing=view.due_missing,
        reset_label="Use the series or your default",
    )


@router.post("/web/profile/reminders")
def save_profile_reminders(
    session: SessionDep,
    chrome: ChromeDep,
    start_amount: Annotated[list[str] | None, Form()] = None,
    start_unit: Annotated[list[str] | None, Form()] = None,
    due_amount: Annotated[list[str] | None, Form()] = None,
    due_unit: Annotated[list[str] | None, Form()] = None,
    at_start: Annotated[str | None, Form()] = None,
    at_due: Annotated[str | None, Form()] = None,
    overdue_kind: Annotated[str, Form()] = "off",
    overdue_amount: Annotated[str, Form()] = "",
    overdue_unit: Annotated[str, Form()] = "minute",
    overdue_clock: Annotated[str, Form()] = "",
    base_updated_at: Annotated[str, Form()] = "",
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    try:
        reminder_service.save_default(
            session,
            user.id,
            _posted(
                start_amount,
                start_unit,
                due_amount,
                due_unit,
                at_start,
                at_due,
                overdue_kind,
                overdue_amount,
                overdue_unit,
                overdue_clock,
                base_updated_at,
            ),
        )
    except DomainError as exc:
        session.rollback()
        return _back("/profile", exc.message)
    return _back("/profile", notice="Reminders saved.")


@router.post(
    "/web/schedules/{series_id}/reminder",
    dependencies=[Depends(require_series(Permission.VIEW_SCHEDULES))],
)
def save_series_reminders(
    series_id: int,
    session: SessionDep,
    chrome: ChromeDep,
    start_amount: Annotated[list[str] | None, Form()] = None,
    start_unit: Annotated[list[str] | None, Form()] = None,
    due_amount: Annotated[list[str] | None, Form()] = None,
    due_unit: Annotated[list[str] | None, Form()] = None,
    at_start: Annotated[str | None, Form()] = None,
    at_due: Annotated[str | None, Form()] = None,
    overdue_kind: Annotated[str, Form()] = "off",
    overdue_amount: Annotated[str, Form()] = "",
    overdue_unit: Annotated[str, Form()] = "minute",
    overdue_clock: Annotated[str, Form()] = "",
    base_updated_at: Annotated[str, Form()] = "",
) -> RedirectResponse:
    return _save_scoped(
        session,
        chrome,
        lambda user_id, draft: reminder_service.save_series_rule(
            session, user_id, series_id, draft
        ),
        _series_path(session, series_id),
        start_amount,
        start_unit,
        due_amount,
        due_unit,
        at_start,
        at_due,
        overdue_kind,
        overdue_amount,
        overdue_unit,
        overdue_clock,
        base_updated_at,
    )


@router.post(
    "/web/schedules/{series_id}/reminder/reset",
    dependencies=[Depends(require_series(Permission.VIEW_SCHEDULES))],
)
def reset_series_reminders(
    series_id: int,
    session: SessionDep,
    chrome: ChromeDep,
    base_updated_at: Annotated[str, Form()] = "",
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    path = _series_path(session, series_id)
    try:
        reminder_service.delete_series_rule(
            session,
            user.id,
            series_id,
            reminder_service.rule_from_lists(
                [],
                [],
                False,
                [],
                [],
                False,
                "off",
                "",
                "minute",
                "",
                base_updated_at,
            ).base_updated_at,
        )
    except NotFoundError:
        session.rollback()
        return _back(path, notice="Using your default.")
    except DomainError as exc:
        session.rollback()
        return _back(path, exc.message)
    return _back(path, notice="Using your default.")


@router.post(
    "/web/issues/{issue_id}/reminder",
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def save_issue_reminders(
    issue_id: int,
    session: SessionDep,
    chrome: ChromeDep,
    start_amount: Annotated[list[str] | None, Form()] = None,
    start_unit: Annotated[list[str] | None, Form()] = None,
    due_amount: Annotated[list[str] | None, Form()] = None,
    due_unit: Annotated[list[str] | None, Form()] = None,
    at_start: Annotated[str | None, Form()] = None,
    at_due: Annotated[str | None, Form()] = None,
    overdue_kind: Annotated[str, Form()] = "off",
    overdue_amount: Annotated[str, Form()] = "",
    overdue_unit: Annotated[str, Form()] = "minute",
    overdue_clock: Annotated[str, Form()] = "",
    base_updated_at: Annotated[str, Form()] = "",
) -> RedirectResponse:
    return _save_scoped(
        session,
        chrome,
        lambda user_id, draft: reminder_service.save_issue_rule(
            session, user_id, issue_id, draft
        ),
        _issue_path(session, issue_id),
        start_amount,
        start_unit,
        due_amount,
        due_unit,
        at_start,
        at_due,
        overdue_kind,
        overdue_amount,
        overdue_unit,
        overdue_clock,
        base_updated_at,
    )


@router.post(
    "/web/issues/{issue_id}/reminder/reset",
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def reset_issue_reminders(
    issue_id: int,
    session: SessionDep,
    chrome: ChromeDep,
    base_updated_at: Annotated[str, Form()] = "",
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    path = _issue_path(session, issue_id)
    try:
        reminder_service.delete_issue_rule(
            session,
            user.id,
            issue_id,
            reminder_service.rule_from_lists(
                [],
                [],
                False,
                [],
                [],
                False,
                "off",
                "",
                "minute",
                "",
                base_updated_at,
            ).base_updated_at,
        )
    except NotFoundError:
        session.rollback()
        return _back(path, notice="Using the series or your default.")
    except DomainError as exc:
        session.rollback()
        return _back(path, exc.message)
    return _back(path, notice="Using the series or your default.")


def _save_scoped(
    session: Session,
    chrome: Chrome,
    save: Callable[[int, RuleWrite], object],
    path: str,
    *fields: object,
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    try:
        save(user.id, reminder_service.rule_from_lists(*_field_lists(fields)))
    except DomainError as exc:
        session.rollback()
        return _back(path, exc.message)
    return _back(path, notice="Reminders saved.")


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _field_lists(
    fields: tuple[object, ...],
) -> tuple[
    list[str],
    list[str],
    bool,
    list[str],
    list[str],
    bool,
    str,
    str,
    str,
    str,
    str,
]:
    start_amount, start_unit, due_amount, due_unit, at_start, at_due, *rest = fields
    kind, amount, unit, clock, base = rest
    return (
        _text_list(start_amount),
        _text_list(start_unit),
        bool(at_start),
        _text_list(due_amount),
        _text_list(due_unit),
        bool(at_due),
        "" if kind is None else str(kind),
        "" if amount is None else str(amount),
        "" if unit is None else str(unit),
        "" if clock is None else str(clock),
        "" if base is None else str(base),
    )


def _posted(
    start_amount: list[str] | None,
    start_unit: list[str] | None,
    due_amount: list[str] | None,
    due_unit: list[str] | None,
    at_start: str | None,
    at_due: str | None,
    overdue_kind: str,
    overdue_amount: str,
    overdue_unit: str,
    overdue_clock: str,
    base_updated_at: str,
) -> RuleWrite:
    return reminder_service.rule_from_lists(
        start_amount or [],
        start_unit or [],
        bool(at_start),
        due_amount or [],
        due_unit or [],
        bool(at_due),
        overdue_kind,
        overdue_amount,
        overdue_unit,
        overdue_clock,
        base_updated_at,
    )


def _series_path(session: Session, series_id: int) -> str:
    from keel.services import projects as project_service
    from keel.services import series as series_service

    series = series_service.get_series(session, series_id)
    project = project_service.get_project(session, series.project_id)
    return f"/projects/{project.key}/schedules/{series.id}"


def _issue_path(session: Session, issue_id: int) -> str:
    from keel.services import projects as project_service

    issue = issue_service.get_issue(session, issue_id)
    project = project_service.get_project(session, issue.project_id)
    return f"/issues/{issue_service.issue_key(issue, project)}"


def _back(
    path: str,
    error: str | None = None,
    notice: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {}
    if error:
        params["error"] = error
    if notice:
        params["notice"] = notice
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(url=f"{path}{query}", status_code=303)


def _stamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat()


def _editor(
    rule: RuleRead | RuleBody | None,
    *,
    action: str,
    reset_action: str | None,
    note: str,
    base: str,
    start_missing: bool = False,
    due_missing: bool = False,
    reset_label: str = "Reset",
) -> SimpleNamespace:
    overdue = None if rule is None else rule.overdue
    clock = ""
    if overdue is not None and overdue.minute_of_day is not None:
        clock = f"{overdue.minute_of_day // 60:02d}:{overdue.minute_of_day % 60:02d}"
    return SimpleNamespace(
        action=action,
        reset_action=reset_action,
        reset_label=reset_label,
        note=note,
        base_updated_at=base,
        start_missing=start_missing,
        due_missing=due_missing,
        start_rows=_rows(None if rule is None else rule.start_offsets),
        due_rows=_rows(None if rule is None else rule.due_offsets),
        at_start=False if rule is None else rule.at_start,
        at_due=False if rule is None else rule.at_due,
        overdue_kind="off" if overdue is None else overdue.kind,
        overdue_amount=""
        if overdue is None or overdue.amount is None
        else overdue.amount,
        overdue_unit="hour"
        if overdue is None or overdue.unit is None
        else overdue.unit,
        overdue_clock=clock,
        units=_UNITS,
    )


def _rows(offsets: list[OffsetBody] | None) -> list[SimpleNamespace]:
    rows = [
        SimpleNamespace(amount=item.amount, unit=item.unit) for item in (offsets or [])
    ]
    rows.append(SimpleNamespace(amount="", unit="hour"))
    return rows
