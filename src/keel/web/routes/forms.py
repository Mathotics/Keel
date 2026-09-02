from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from keel.domain.duration import parse_duration
from keel.domain.enums import DependencyKind, IssueStatus, IssueType
from keel.domain.errors import DomainError
from keel.services import comments as comment_service
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.identity import USER_COOKIE
from keel.web.context import ChromeDep, SessionDep

router = APIRouter(prefix="/web")

SEE_OTHER = 303


def _back(
    path: str,
    error: str | None = None,
    notice: str | None = None,
) -> RedirectResponse:
    parsed = urlparse(path)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if error:
        params["error"] = error
    if notice:
        params["notice"] = notice
    target = urlunparse(parsed._replace(query=urlencode(params)))
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


@router.post("/issues")
def create_issue_from_page(
    session: SessionDep,
    chrome: ChromeDep,
    project_id: Annotated[str, Form()] = "",
    type: Annotated[IssueType, Form()] = IssueType.STORY,
    title: Annotated[str, Form()] = "",
) -> RedirectResponse:
    chosen = _optional_id(project_id)
    if chosen is None:
        return _back("/create", "Choose a project.")
    project = project_service.get_project(session, chosen)
    here = f"/create?project={project.key}"
    try:
        issue = issue_service.create_issue(
            session,
            project.id,
            type=type,
            title=title,
            reporter_id=(
                None if chrome.current_user is None else chrome.current_user.id
            ),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(f"/issues/{project.key}-{issue.number}")


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
    estimate: Annotated[str, Form()] = "",
    remaining: Annotated[str, Form()] = "",
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
            estimate_minutes=parse_duration(estimate),
            remaining_minutes=parse_duration(remaining),
        )
    except DomainError as exc:
        session.rollback()
        return _back(f"/create?project={key}", exc.message)
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


@router.post("/issues/{issue_id}/estimate")
def update_issue_estimate(
    session: SessionDep,
    issue_id: int,
    estimate: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            estimate_minutes=parse_duration(estimate),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/remaining")
def update_issue_remaining(
    session: SessionDep,
    issue_id: int,
    remaining: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            remaining_minutes=parse_duration(remaining),
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


def _dependency_ends(
    issue_id: int,
    other_id: int,
    relation: str,
) -> tuple[int, int, DependencyKind] | None:
    if relation == "blocks":
        return issue_id, other_id, DependencyKind.BLOCKS
    if relation == "blocked_by":
        return other_id, issue_id, DependencyKind.BLOCKS
    if relation == "relates_to":
        return issue_id, other_id, DependencyKind.RELATES_TO
    return None


@router.post("/issues/{issue_id}/dependencies")
def create_issue_dependency(
    session: SessionDep,
    issue_id: int,
    other_id: Annotated[str, Form()] = "",
    relation: Annotated[str, Form()] = "blocks",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    chosen = _optional_id(other_id)
    if chosen is None:
        return _back(here, "Choose an issue to link.")
    ends = _dependency_ends(issue_id, chosen, relation)
    if ends is None:
        return _back(here, "That is not a valid dependency kind.")
    source_id, target_id, kind = ends
    try:
        dependency_service.create_dependency(session, source_id, target_id, kind)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/dependencies/{dependency_id}/delete")
def delete_issue_dependency(
    session: SessionDep,
    dependency_id: int,
    return_to: Annotated[str, Form(alias="next")] = "",
) -> RedirectResponse:
    dependency = dependency_service.get_dependency(session, dependency_id)
    here = return_to or _issue_here(session, dependency.source_id)
    try:
        dependency_service.delete_dependency(session, dependency_id)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/comments")
def create_issue_comment(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    body: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        comment_service.create_comment(
            session,
            issue_id,
            body,
            author_id=None if chrome.current_user is None else chrome.current_user.id,
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/comments/{comment_id}/delete")
def delete_issue_comment(
    session: SessionDep,
    comment_id: int,
    return_to: Annotated[str, Form(alias="next")] = "",
) -> RedirectResponse:
    comment = comment_service.get_comment(session, comment_id)
    here = return_to or _issue_here(session, comment.issue_id)
    try:
        comment_service.delete_comment(session, comment_id)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


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
