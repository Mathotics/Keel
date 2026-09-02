from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from keel.domain.enums import IssueStatus, IssueType
from keel.domain.errors import DomainError
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.identity import USER_COOKIE
from keel.web.context import SessionDep

router = APIRouter(prefix="/web")

SEE_OTHER = 303


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
    target = path if not params else f"{path}?{urlencode(params)}"
    return RedirectResponse(url=target, status_code=SEE_OTHER)


def _optional_id(raw: str) -> int | None:
    return int(raw) if raw.strip().isdigit() else None


@router.post("/user")
def switch_user(
    user: Annotated[str, Form()],
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    response = _back(return_to or "/")
    response.set_cookie(USER_COOKIE, user, samesite="lax")
    return response


@router.post("/users")
def create_user(
    session: SessionDep,
    display_name: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        user_service.create_user(session, display_name)
    except DomainError as exc:
        session.rollback()
        return _back("/users", exc.message)
    return _back("/users")


@router.post("/users/{user_id}/rename")
def rename_user(
    session: SessionDep,
    user_id: int,
    display_name: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        user_service.rename_user(session, user_id, display_name)
    except DomainError as exc:
        session.rollback()
        return _back("/users", exc.message)
    return _back("/users")


@router.post("/users/{user_id}/delete")
def delete_user(session: SessionDep, user_id: int) -> RedirectResponse:
    try:
        user_service.delete_user(session, user_id)
    except DomainError as exc:
        session.rollback()
        return _back("/users", exc.message)
    return _back("/users")


@router.post("/projects")
def create_project(
    session: SessionDep,
    key: Annotated[str, Form()],
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        project = project_service.create_project(session, key, name, description)
    except DomainError as exc:
        session.rollback()
        return _back("/projects", exc.message)
    return _back(f"/projects/{project.key}")


@router.post("/projects/{project_id}/update")
def update_project(
    session: SessionDep,
    project_id: int,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        project = project_service.update_project(session, project_id, name, description)
    except DomainError as exc:
        session.rollback()
        key = project_service.get_project(session, project_id).key
        return _back(f"/projects/{key}", exc.message)
    return _back(f"/projects/{project.key}")


@router.post("/projects/{project_id}/delete")
def delete_project(session: SessionDep, project_id: int) -> RedirectResponse:
    project_service.delete_project(session, project_id)
    return _back("/projects")


@router.post("/projects/{project_id}/issues")
def create_issue(
    session: SessionDep,
    project_id: int,
    type: Annotated[IssueType, Form()],
    title: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    status: Annotated[IssueStatus, Form()] = IssueStatus.TODO,
    parent_id: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    reporter_id: Annotated[str, Form()] = "",
    due_at: Annotated[str, Form()] = "",
    sprint_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    key = project_service.get_project(session, project_id).key
    try:
        issue = issue_service.create_issue(
            session,
            project_id,
            type=type,
            title=title,
            description=description,
            status=status,
            parent_id=_optional_id(parent_id),
            reporter_id=_optional_id(reporter_id),
            assignee_id=_optional_id(assignee_id),
            due_at=issue_service.parse_due_at(due_at),
            sprint_id=_optional_id(sprint_id),
        )
    except DomainError as exc:
        session.rollback()
        return _back(f"/projects/{key}/issues/new", exc.message)
    return _back(f"/issues/{key}-{issue.number}")


def _issue_here(session: SessionDep, issue_id: int) -> str:
    issue = issue_service.get_issue(session, issue_id)
    key = project_service.get_project(session, issue.project_id).key
    return f"/issues/{key}-{issue.number}"


@router.post("/issues/{issue_id}/title")
def update_issue_title(
    session: SessionDep,
    issue_id: int,
    title: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(session, issue_id, title=title)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/type")
def update_issue_type(
    session: SessionDep,
    issue_id: int,
    type: Annotated[IssueType, Form()],
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(session, issue_id, type=type)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/description")
def update_issue_description(
    session: SessionDep,
    issue_id: int,
    description: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(session, issue_id, description=description)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/parent")
def update_issue_parent(
    session: SessionDep,
    issue_id: int,
    parent_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            parent_id=_optional_id(parent_id),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/due")
def update_issue_due(
    session: SessionDep,
    issue_id: int,
    due_at: Annotated[str, Form()] = "",
) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    key = project_service.get_project(session, issue.project_id).key
    here = f"/issues/{key}-{issue.number}"
    try:
        issue_service.update_issue(
            session,
            issue_id,
            due_at=issue_service.parse_due_at(due_at),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/assignee")
def update_issue_assignee(
    session: SessionDep,
    issue_id: int,
    assignee_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    key = project_service.get_project(session, issue.project_id).key
    here = f"/issues/{key}-{issue.number}"
    try:
        issue_service.update_issue(
            session,
            issue_id,
            assignee_id=_optional_id(assignee_id),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/status")
def move_issue_status(
    session: SessionDep,
    issue_id: int,
    status: Annotated[IssueStatus, Form()],
    return_to: Annotated[str, Form(alias="next")] = "",
) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    project = project_service.get_project(session, issue.project_id)
    board = f"/projects/{project.key}/board"
    try:
        issue_service.update_issue(session, issue_id, status=status)
    except DomainError as exc:
        session.rollback()
        return _back(return_to or board, exc.message)
    return _back(return_to or board)


@router.post("/issues/{issue_id}/delete")
def delete_issue(session: SessionDep, issue_id: int) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    project = project_service.get_project(session, issue.project_id)
    here = f"/issues/{project.key}-{issue.number}"
    try:
        issue_service.delete_issue(session, issue_id)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(f"/projects/{project.key}")


def _sprint_page(session: SessionDep, sprint_id: int) -> str:
    sprint = sprint_service.get_sprint(session, sprint_id)
    key = project_service.get_project(session, sprint.project_id).key
    return f"/projects/{key}/sprints/{sprint.id}"


def _carry_notice(session: SessionDep, result: sprint_service.SprintCompletion) -> str:
    count = result.carried_over
    if count == 0:
        return "No unfinished issues to carry."
    noun = "issue" if count == 1 else "issues"
    if result.carried_to_sprint_id is None:
        return f"{count} unfinished {noun} returned to the backlog."
    destination = sprint_service.get_sprint(session, result.carried_to_sprint_id)
    return f"{count} unfinished {noun} moved to {destination.name}."


@router.post("/issues/{issue_id}/sprint")
def update_issue_sprint(
    session: SessionDep,
    issue_id: int,
    sprint_id: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form(alias="next")] = "",
) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    project = project_service.get_project(session, issue.project_id)
    here = f"/issues/{project.key}-{issue.number}"
    try:
        issue_service.update_issue(
            session,
            issue_id,
            sprint_id=_optional_id(sprint_id),
        )
    except DomainError as exc:
        session.rollback()
        return _back(return_to or here, exc.message)
    return _back(return_to or here)


@router.post("/projects/{project_id}/sprints")
def create_sprint(
    session: SessionDep,
    project_id: int,
    name: Annotated[str, Form()],
    goal: Annotated[str, Form()] = "",
    starts_on: Annotated[str, Form()] = "",
    ends_on: Annotated[str, Form()] = "",
) -> RedirectResponse:
    key = project_service.get_project(session, project_id).key
    listing = f"/projects/{key}/sprints"
    try:
        sprint = sprint_service.create_sprint(
            session,
            project_id,
            name=name,
            goal=goal,
            starts_on=sprint_service.parse_date(starts_on),
            ends_on=sprint_service.parse_date(ends_on),
        )
    except DomainError as exc:
        session.rollback()
        return _back(listing, exc.message)
    return _back(f"/projects/{key}/sprints/{sprint.id}")


@router.post("/sprints/{sprint_id}/update")
def update_sprint(
    session: SessionDep,
    sprint_id: int,
    name: Annotated[str, Form()],
    goal: Annotated[str, Form()] = "",
    starts_on: Annotated[str, Form()] = "",
    ends_on: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _sprint_page(session, sprint_id)
    try:
        sprint_service.update_sprint(
            session,
            sprint_id,
            name=name,
            goal=goal,
            starts_on=sprint_service.parse_date(starts_on),
            ends_on=sprint_service.parse_date(ends_on),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/sprints/{sprint_id}/delete")
def delete_sprint(session: SessionDep, sprint_id: int) -> RedirectResponse:
    sprint = sprint_service.get_sprint(session, sprint_id)
    key = project_service.get_project(session, sprint.project_id).key
    listing = f"/projects/{key}/sprints"
    try:
        sprint_service.delete_sprint(session, sprint_id)
    except DomainError as exc:
        session.rollback()
        return _back(_sprint_page(session, sprint_id), exc.message)
    return _back(listing)


@router.post("/sprints/{sprint_id}/start")
def start_sprint(session: SessionDep, sprint_id: int) -> RedirectResponse:
    here = _sprint_page(session, sprint_id)
    try:
        sprint_service.start_sprint(session, sprint_id)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/sprints/{sprint_id}/complete")
def complete_sprint(session: SessionDep, sprint_id: int) -> RedirectResponse:
    here = _sprint_page(session, sprint_id)
    try:
        result = sprint_service.complete_sprint(session, sprint_id)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here, notice=_carry_notice(session, result))
