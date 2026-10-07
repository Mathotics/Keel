from datetime import date
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.cadence import MAX_SPRINT_AHEAD, MIN_SPRINT_AHEAD
from keel.domain.duration import parse_duration
from keel.domain.enums import (
    INITIAL_PRIORITY,
    DependencyKind,
    EditScope,
    IssuePriority,
    IssueStatus,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
    SprintCadence,
)
from keel.domain.errors import (
    CannotDeleteSelfError,
    DomainError,
    InvalidSprintCadenceError,
    NotFoundError,
)
from keel.domain.hierarchy import child_type_of
from keel.domain.labels import parse_label_names
from keel.domain.schedule import parse_clock
from keel.services import auto_sprint
from keel.services import comments as comment_service
from keel.services import dependencies as dependency_service
from keel.services import history as history_service
from keel.services import issues as issue_service
from keel.services import labels as label_service
from keel.services import lookup as lookup_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import Chrome, ChromeDep, SessionDep
from keel.web.home_layout import (
    HOME_COOKIE,
    HOME_COOKIE_MAX_AGE,
    HomeLayout,
    apply_move,
    apply_posted_order,
    encode_layout,
    hide_panel,
    parse_layout,
    show_panel,
)
from keel.web.inbox import (
    INBOX_COOKIE,
    INBOX_COOKIE_MAX_AGE,
    encode_collapsed,
    parse_collapsed,
)
from keel.web.nav import (
    NAV_COOKIE,
    NAV_COOKIE_MAX_AGE,
    encode_order,
    merge_visible,
    move_item,
    parse_order,
)
from keel.web.routes.pages import IssueDraft, render_create_page

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


def _posted_issue(
    session: SessionDep,
    raw_id: str,
    raw_query: str,
    *,
    project_id: int | None,
    message: str,
) -> int | None:
    return lookup_service.resolve_posted_issue(
        session,
        raw_id,
        raw_query,
        project_id=project_id,
        message=message,
    )


def _posted_user(session: SessionDep, raw_id: str, raw_query: str) -> int | None:
    return lookup_service.resolve_posted_user(session, raw_id, raw_query)


def _assign_to_me(raw: str) -> bool:
    return raw.strip() == "1"


def _parent_label(
    session: SessionDep,
    project_id: int,
    raw_id: str,
    raw_query: str,
) -> str:
    chosen = raw_id.strip()
    if not chosen.isdigit():
        return raw_query
    project = project_service.get_project(session, project_id)
    try:
        return lookup_service.parent_field_value(session, int(chosen), project)
    except NotFoundError:
        return raw_query


def _remember_nav(
    response: RedirectResponse,
    order: tuple[str, ...],
) -> RedirectResponse:
    response.set_cookie(
        NAV_COOKIE,
        encode_order(order),
        max_age=NAV_COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
    )
    return response


@router.post("/nav")
def save_nav_order(
    request: Request,
    order: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    merged = merge_visible(
        parse_order(request.cookies.get(NAV_COOKIE)),
        order.split(","),
    )
    return _remember_nav(_back(return_to or "/"), merged)


@router.post("/inbox")
def save_inbox_collapsed(
    collapsed: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    response = _back(return_to or "/")
    response.set_cookie(
        INBOX_COOKIE,
        encode_collapsed(parse_collapsed(collapsed)),
        max_age=INBOX_COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
    )
    return response


def _remember_home(response: RedirectResponse, layout: HomeLayout) -> RedirectResponse:
    response.set_cookie(
        HOME_COOKIE,
        encode_layout(layout),
        max_age=HOME_COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
    )
    return response


@router.post("/home/move")
def move_home_panel(
    request: Request,
    item: Annotated[str, Form()],
    direction: Annotated[str, Form()],
    visible: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    layout = parse_layout(request.cookies.get(HOME_COOKIE))
    moved = apply_move(layout, visible.split(","), item, direction)
    return _remember_home(_back(return_to or "/"), moved)


@router.post("/home/order")
def save_home_order(
    request: Request,
    order: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    layout = parse_layout(request.cookies.get(HOME_COOKIE))
    posted = apply_posted_order(layout, order.split(","))
    return _remember_home(_back(return_to or "/"), posted)


@router.post("/home/hide")
def hide_home_panel(
    request: Request,
    panel: Annotated[str, Form()],
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    layout = parse_layout(request.cookies.get(HOME_COOKIE))
    return _remember_home(_back(return_to or "/"), hide_panel(layout, panel))


@router.post("/home/show")
def show_home_panel(
    request: Request,
    panel: Annotated[str, Form()],
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    layout = parse_layout(request.cookies.get(HOME_COOKIE))
    return _remember_home(_back(return_to or "/"), show_panel(layout, panel))


@router.post("/nav/move")
def move_nav_item(
    request: Request,
    item: Annotated[str, Form()],
    direction: Annotated[str, Form()],
    visible: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    moved = move_item(visible.split(","), item, direction)
    merged = merge_visible(parse_order(request.cookies.get(NAV_COOKIE)), moved)
    return _remember_nav(_back(return_to or "/"), merged)


@router.post("/users")
def create_user(
    session: SessionDep,
    display_name: Annotated[str, Form()],
    password: Annotated[str, Form()] = "",
    confirm: Annotated[str, Form()] = "",
    username: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        user_service.create_user(
            session,
            display_name,
            username.strip() or None,
            password,
            confirm=confirm,
            require_password=True,
        )
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
def delete_user(
    session: SessionDep,
    chrome: ChromeDep,
    user_id: int,
) -> RedirectResponse:
    if chrome.current_user is not None and chrome.current_user.id == user_id:
        refused = CannotDeleteSelfError(
            "Sign in as someone else before deleting this account.",
        )
        return _back("/users", refused.message)
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
    sprint_cadence: Annotated[str, Form()] = SprintCadence.OFF.value,
    sprint_cadence_days: Annotated[str, Form()] = "",
    sprint_ahead: Annotated[str, Form()] = "0",
) -> RedirectResponse:
    try:
        project = project_service.update_project(
            session,
            project_id,
            name,
            description,
            sprint_cadence=_parse_cadence(sprint_cadence),
            sprint_cadence_days=_parse_cadence_days(sprint_cadence_days),
            sprint_ahead=_parse_sprint_ahead(sprint_ahead),
        )
    except DomainError as exc:
        session.rollback()
        key = project_service.get_project(session, project_id).key
        return _back(f"/projects/{key}", exc.message)
    notice = project.auto_sprint_notice or None
    return _back(f"/projects/{project.key}", notice=notice)


@router.post("/projects/{project_id}/delete")
def delete_project(session: SessionDep, project_id: int) -> RedirectResponse:
    project_service.delete_project(session, project_id)
    return _back("/projects")


@router.post("/issues", response_model=None)
def create_issue_from_page(
    request: Request,
    session: SessionDep,
    chrome: ChromeDep,
    project_id: Annotated[str, Form()] = "",
    type: Annotated[IssueType, Form()] = IssueType.STORY,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    status: Annotated[IssueStatus, Form()] = IssueStatus.TODO,
    priority: Annotated[IssuePriority, Form()] = INITIAL_PRIORITY,
    parent_id: Annotated[str, Form()] = "",
    parent_query: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    assignee_query: Annotated[str, Form()] = "",
    start_at: Annotated[str, Form()] = "",
    due_at: Annotated[str, Form()] = "",
    sprint_id: Annotated[str, Form()] = "",
    estimate: Annotated[str, Form()] = "",
    remaining: Annotated[str, Form()] = "",
    labels: Annotated[str, Form()] = "",
    assign_to_me: Annotated[str, Form()] = "",
) -> RedirectResponse | HTMLResponse:
    chosen = _optional_id(project_id)
    if chosen is None:
        return _back("/create", "Choose a project.")
    project = project_service.get_project(session, chosen)
    here = f"/create?project={project.key}"
    if _assign_to_me(assign_to_me):
        if chrome.current_user is None:
            return _back(here, "Sign in to assign this to yourself.")
        return render_create_page(
            request,
            chrome,
            session,
            project=project.key,
            draft=IssueDraft(
                type=type,
                title=title,
                description=description,
                status=status,
                priority=priority,
                parent_label=_parent_label(
                    session,
                    project.id,
                    parent_id,
                    parent_query,
                ),
                assignee_label=chrome.current_user.display_name,
                sprint_id=sprint_id,
                start_at=start_at,
                due_at=due_at,
                estimate=estimate,
                remaining=remaining,
                labels=labels,
            ),
        )
    try:
        issue = issue_service.create_issue(
            session,
            project.id,
            type=type,
            title=title,
            description=description,
            status=status,
            priority=priority,
            parent_id=_posted_issue(
                session,
                parent_id,
                parent_query,
                project_id=project.id,
                message=lookup_service.PARENT_MESSAGE,
            ),
            reporter_id=(
                None if chrome.current_user is None else chrome.current_user.id
            ),
            assignee_id=_posted_user(session, assignee_id, assignee_query),
            start_at=issue_service.parse_start_at(start_at),
            due_at=issue_service.parse_due_at(due_at),
            sprint_id=_optional_id(sprint_id),
            estimate_minutes=parse_duration(estimate),
            remaining_minutes=parse_duration(remaining),
            labels=labels,
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
    priority: Annotated[IssuePriority, Form()] = INITIAL_PRIORITY,
    parent_id: Annotated[str, Form()] = "",
    parent_query: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    assignee_query: Annotated[str, Form()] = "",
    reporter_id: Annotated[str, Form()] = "",
    start_at: Annotated[str, Form()] = "",
    due_at: Annotated[str, Form()] = "",
    sprint_id: Annotated[str, Form()] = "",
    estimate: Annotated[str, Form()] = "",
    remaining: Annotated[str, Form()] = "",
    labels: Annotated[str, Form()] = "",
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
            priority=priority,
            parent_id=_posted_issue(
                session,
                parent_id,
                parent_query,
                project_id=project_id,
                message=lookup_service.PARENT_MESSAGE,
            ),
            reporter_id=_optional_id(reporter_id),
            assignee_id=_posted_user(session, assignee_id, assignee_query),
            start_at=issue_service.parse_start_at(start_at),
            due_at=issue_service.parse_due_at(due_at),
            sprint_id=_optional_id(sprint_id),
            estimate_minutes=parse_duration(estimate),
            remaining_minutes=parse_duration(remaining),
            labels=labels,
        )
    except DomainError as exc:
        session.rollback()
        return _back(f"/create?project={key}", exc.message)
    return _back(f"/issues/{key}-{issue.number}")


def _actor_name(chrome: Chrome) -> str:
    if chrome.current_user is None:
        return history_service.SYSTEM_ACTOR
    return chrome.current_user.display_name


def _issue_here(session: SessionDep, issue_id: int) -> str:
    issue = issue_service.get_issue(session, issue_id)
    key = project_service.get_project(session, issue.project_id).key
    return f"/issues/{key}-{issue.number}"


@router.post("/issues/{issue_id}/title")
def update_issue_title(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    title: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            title=title,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/type")
def update_issue_type(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    type: Annotated[IssueType, Form()],
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            type=type,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/priority")
def update_issue_priority(
    session: SessionDep,
    issue_id: int,
    priority: Annotated[IssuePriority, Form()],
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(session, issue_id, priority=priority)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/description")
def update_issue_description(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    description: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            description=description,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/children")
def create_child_issue(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    title: Annotated[str, Form()] = "",
) -> RedirectResponse:
    parent = issue_service.get_issue(session, issue_id)
    here = _issue_here(session, issue_id)
    child_type = child_type_of(parent.type)
    if child_type is None:
        return _back(here, "A subtask cannot have children.")
    try:
        issue_service.create_issue(
            session,
            parent.project_id,
            type=child_type,
            title=title,
            parent_id=parent.id,
            reporter_id=(
                None if chrome.current_user is None else chrome.current_user.id
            ),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/parent")
def update_issue_parent(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    parent_id: Annotated[str, Form()] = "",
    parent_query: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue = issue_service.get_issue(session, issue_id)
        issue_service.update_issue(
            session,
            issue_id,
            parent_id=_posted_issue(
                session,
                parent_id,
                parent_query,
                project_id=issue.project_id,
                message=lookup_service.PARENT_MESSAGE,
            ),
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/estimate")
def update_issue_estimate(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    estimate: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            estimate_minutes=parse_duration(estimate),
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/remaining")
def update_issue_remaining(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    remaining: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        issue_service.update_issue(
            session,
            issue_id,
            remaining_minutes=parse_duration(remaining),
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/labels")
def add_issue_label(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    name: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        label_service.add_issue_label(
            session,
            issue_id,
            name,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/labels/{label_id}/delete")
def remove_issue_label(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    label_id: int,
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        label_service.remove_issue_label(
            session,
            issue_id,
            label_id,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/dates")
def update_issue_dates(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    start_at: Annotated[str, Form()] = "",
    due_at: Annotated[str, Form()] = "",
    scope: Annotated[EditScope, Form()] = EditScope.THIS,
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    issue = issue_service.get_issue(session, issue_id)
    parsed_start = issue_service.parse_start_at(start_at)
    parsed_due = issue_service.parse_due_at(due_at)
    try:
        if issue.series_id is None:
            issue_service.update_issue(
                session,
                issue_id,
                start_at=parsed_start,
                due_at=parsed_due,
                actor_name=_actor_name(chrome),
            )
        else:
            series_service.apply_occurrence_edit(
                session,
                issue_id,
                scope,
                start_at=parsed_start,
                due_at=parsed_due,
                actor_name=_actor_name(chrome),
            )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/due")
def update_issue_due(
    session: SessionDep,
    chrome: ChromeDep,
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
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/assignee")
def update_issue_assignee(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    assignee_id: Annotated[str, Form()] = "",
    assignee_query: Annotated[str, Form()] = "",
    assign_to_me: Annotated[str, Form()] = "",
) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    key = project_service.get_project(session, issue.project_id).key
    here = f"/issues/{key}-{issue.number}"
    try:
        if _assign_to_me(assign_to_me):
            if chrome.current_user is None:
                return _back(here, "Sign in to assign this to yourself.")
            chosen_assignee: int | None = chrome.current_user.id
        else:
            chosen_assignee = _posted_user(session, assignee_id, assignee_query)
        issue_service.update_issue(
            session,
            issue_id,
            assignee_id=chosen_assignee,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/status")
def move_issue_status(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    status: Annotated[IssueStatus, Form()],
    return_to: Annotated[str, Form(alias="next")] = "",
) -> RedirectResponse:
    issue = issue_service.get_issue(session, issue_id)
    project = project_service.get_project(session, issue.project_id)
    board = f"/projects/{project.key}/board"
    try:
        issue_service.update_issue(
            session,
            issue_id,
            status=status,
            actor_name=_actor_name(chrome),
        )
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
    other_query: Annotated[str, Form()] = "",
    relation: Annotated[str, Form()] = "blocks",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        chosen = _posted_issue(
            session,
            other_id,
            other_query,
            project_id=None,
            message=lookup_service.LINK_MESSAGE,
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    if chosen is None:
        return _back(here, lookup_service.LINK_MESSAGE)
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
    chrome: ChromeDep,
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
            actor_name=_actor_name(chrome),
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
        auto_sprint.delete_sprint(session, sprint_id)
    except DomainError as exc:
        session.rollback()
        return _back(_sprint_page(session, sprint_id), exc.message)
    project = project_service.get_project_by_key(session, key)
    return _back(listing, notice=project.auto_sprint_notice or None)


@router.post("/sprints/{sprint_id}/start")
def start_sprint(session: SessionDep, sprint_id: int) -> RedirectResponse:
    here = _sprint_page(session, sprint_id)
    try:
        auto_sprint.start_sprint(session, sprint_id)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/sprints/{sprint_id}/complete")
def complete_sprint(
    session: SessionDep,
    chrome: ChromeDep,
    sprint_id: int,
) -> RedirectResponse:
    here = _sprint_page(session, sprint_id)
    try:
        result = auto_sprint.complete_sprint(
            session,
            sprint_id,
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    project = project_service.get_project(session, result.sprint.project_id)
    if project.sprint_cadence is not SprintCadence.OFF and project.auto_sprint_notice:
        notice = project.auto_sprint_notice
    else:
        notice = _carry_notice(session, result)
    return _back(here, notice=notice)


@router.post("/projects/{project_id}/schedules")
def create_schedule(
    session: SessionDep,
    chrome: ChromeDep,
    project_id: int,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    type: Annotated[IssueType, Form()] = IssueType.STORY,
    priority: Annotated[IssuePriority, Form()] = INITIAL_PRIORITY,
    spawn_mode: Annotated[SeriesSpawnMode, Form()] = SeriesSpawnMode.CALENDAR,
    sprint_basis: Annotated[SeriesSprintBasis, Form()] = SeriesSprintBasis.DUE_ON,
    freq: Annotated[RecurrenceFreq, Form()] = RecurrenceFreq.WEEKLY,
    interval: Annotated[str, Form()] = "1",
    starts_on: Annotated[str, Form()] = "",
    weekday: Annotated[list[str] | None, Form()] = None,
    month_day: Annotated[str, Form()] = "",
    nth_week: Annotated[str, Form()] = "",
    month: Annotated[str, Form()] = "",
    look_ahead_n: Annotated[str, Form()] = "1",
    start_offset_days: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    due_offset_days: Annotated[str, Form()] = "",
    due_time: Annotated[str, Form()] = "",
    end_mode: Annotated[str, Form()] = "never",
    ends_on: Annotated[str, Form()] = "",
    occurrence_count: Annotated[str, Form()] = "",
    parent_id: Annotated[str, Form()] = "",
    parent_query: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    assignee_query: Annotated[str, Form()] = "",
    labels: Annotated[str, Form()] = "",
) -> RedirectResponse:
    project = project_service.get_project(session, project_id)
    form_tab = f"/projects/{project.key}/schedules?tab=new"
    try:
        series = series_service.create_series(
            session,
            project.id,
            title=title,
            description=description,
            type=type,
            priority=priority,
            spawn_mode=spawn_mode,
            sprint_basis=sprint_basis,
            freq=freq,
            starts_on=_required_date(starts_on),
            interval=_positive_int(interval, "Repeat interval must be at least 1."),
            weekdays=_weekdays(weekday),
            month_day=_optional_int(month_day),
            nth_week=_optional_signed_int(nth_week),
            month=_optional_int(month),
            ends_on=_end_date(end_mode, ends_on),
            occurrence_count=_end_count(end_mode, occurrence_count),
            look_ahead_n=_positive_int(look_ahead_n, "Look-ahead must be at least 1."),
            start_offset_days=_optional_offset(start_offset_days),
            start_minute_of_day=_optional_clock(start_time),
            due_offset_days=_optional_offset(due_offset_days),
            due_minute_of_day=_optional_clock(due_time),
            parent_id=_posted_issue(
                session,
                parent_id,
                parent_query,
                project_id=project.id,
                message=lookup_service.PARENT_MESSAGE,
            ),
            assignee_id=_posted_user(session, assignee_id, assignee_query),
            labels=parse_label_names(labels),
            reporter_id=(
                None if chrome.current_user is None else chrome.current_user.id
            ),
        )
    except DomainError as exc:
        session.rollback()
        return _back(form_tab, exc.message)
    return _back(f"/projects/{project.key}/schedules/{series.id}")


@router.post("/schedules/{series_id}/update")
def update_schedule(
    session: SessionDep,
    series_id: int,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    type: Annotated[IssueType, Form()] = IssueType.STORY,
    priority: Annotated[IssuePriority, Form()] = INITIAL_PRIORITY,
    spawn_mode: Annotated[SeriesSpawnMode, Form()] = SeriesSpawnMode.CALENDAR,
    sprint_basis: Annotated[SeriesSprintBasis, Form()] = SeriesSprintBasis.DUE_ON,
    freq: Annotated[RecurrenceFreq, Form()] = RecurrenceFreq.WEEKLY,
    interval: Annotated[str, Form()] = "1",
    starts_on: Annotated[str, Form()] = "",
    weekday: Annotated[list[str] | None, Form()] = None,
    month_day: Annotated[str, Form()] = "",
    nth_week: Annotated[str, Form()] = "",
    month: Annotated[str, Form()] = "",
    look_ahead_n: Annotated[str, Form()] = "1",
    start_offset_days: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    due_offset_days: Annotated[str, Form()] = "",
    due_time: Annotated[str, Form()] = "",
    end_mode: Annotated[str, Form()] = "never",
    ends_on: Annotated[str, Form()] = "",
    occurrence_count: Annotated[str, Form()] = "",
    parent_id: Annotated[str, Form()] = "",
    parent_query: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    assignee_query: Annotated[str, Form()] = "",
    labels: Annotated[str, Form()] = "",
) -> RedirectResponse:
    series = series_service.get_series(session, series_id)
    project = project_service.get_project(session, series.project_id)
    here = f"/projects/{project.key}/schedules/{series.id}"
    try:
        series_service.update_series(
            session,
            series.id,
            title=title,
            description=description,
            type=type,
            priority=priority,
            spawn_mode=spawn_mode,
            sprint_basis=sprint_basis,
            freq=freq,
            interval=_positive_int(interval, "Repeat interval must be at least 1."),
            weekdays=_weekdays(weekday),
            month_day=_optional_int(month_day),
            nth_week=_optional_signed_int(nth_week),
            month=_optional_int(month),
            starts_on=_required_date(starts_on),
            ends_on=_end_date(end_mode, ends_on),
            occurrence_count=_end_count(end_mode, occurrence_count),
            look_ahead_n=_positive_int(look_ahead_n, "Look-ahead must be at least 1."),
            start_offset_days=_optional_offset(start_offset_days),
            start_minute_of_day=_optional_clock(start_time),
            due_offset_days=_optional_offset(due_offset_days),
            due_minute_of_day=_optional_clock(due_time),
            parent_id=_posted_issue(
                session,
                parent_id,
                parent_query,
                project_id=project.id,
                message=lookup_service.PARENT_MESSAGE,
            ),
            assignee_id=_posted_user(session, assignee_id, assignee_query),
            labels=parse_label_names(labels),
        )
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


@router.post("/schedules/{series_id}/pause")
def pause_schedule(session: SessionDep, series_id: int) -> RedirectResponse:
    return _schedule_state(session, series_id, SeriesState.PAUSED)


@router.post("/schedules/{series_id}/resume")
def resume_schedule(session: SessionDep, series_id: int) -> RedirectResponse:
    return _schedule_state(session, series_id, SeriesState.ACTIVE)


@router.post("/schedules/{series_id}/delete")
def delete_schedule(session: SessionDep, series_id: int) -> RedirectResponse:
    series = series_service.get_series(session, series_id)
    project = project_service.get_project(session, series.project_id)
    listing = f"/projects/{project.key}/schedules"
    try:
        series_service.delete_series(session, series_id)
    except DomainError as exc:
        session.rollback()
        return _back(
            f"/projects/{project.key}/schedules/{series.id}",
            exc.message,
        )
    return _back(listing, notice="Schedule deleted. Existing issues remain.")


@router.post("/issues/{issue_id}/repeat")
def make_issue_repeating(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    spawn_mode: Annotated[SeriesSpawnMode, Form()] = SeriesSpawnMode.CALENDAR,
    sprint_basis: Annotated[SeriesSprintBasis, Form()] = SeriesSprintBasis.DUE_ON,
    freq: Annotated[RecurrenceFreq, Form()] = RecurrenceFreq.WEEKLY,
    interval: Annotated[str, Form()] = "1",
    starts_on: Annotated[str, Form()] = "",
    weekday: Annotated[list[str] | None, Form()] = None,
    month_day: Annotated[str, Form()] = "",
    nth_week: Annotated[str, Form()] = "",
    month: Annotated[str, Form()] = "",
    look_ahead_n: Annotated[str, Form()] = "1",
    start_offset_days: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    due_offset_days: Annotated[str, Form()] = "",
    due_time: Annotated[str, Form()] = "",
    end_mode: Annotated[str, Form()] = "never",
    ends_on: Annotated[str, Form()] = "",
    occurrence_count: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    issue = issue_service.get_issue(session, issue_id)
    try:
        series_service.create_series(
            session,
            issue.project_id,
            title=issue.title,
            description=issue.description,
            type=issue.type,
            priority=issue.priority,
            spawn_mode=spawn_mode,
            sprint_basis=sprint_basis,
            freq=freq,
            starts_on=_required_date(starts_on),
            interval=_positive_int(interval, "Repeat interval must be at least 1."),
            weekdays=_weekdays(weekday),
            month_day=_optional_int(month_day),
            nth_week=_optional_signed_int(nth_week),
            month=_optional_int(month),
            ends_on=_end_date(end_mode, ends_on),
            occurrence_count=_end_count(end_mode, occurrence_count),
            look_ahead_n=_positive_int(look_ahead_n, "Look-ahead must be at least 1."),
            start_offset_days=_optional_offset(start_offset_days),
            start_minute_of_day=_optional_clock(start_time),
            due_offset_days=_optional_offset(due_offset_days),
            due_minute_of_day=_optional_clock(due_time),
            parent_id=issue.parent_id,
            assignee_id=issue.assignee_id,
            reporter_id=(
                None if chrome.current_user is None else chrome.current_user.id
            ),
            seed_issue_id=issue.id,
        )
    except DomainError as exc:
        session.rollback()
        return _back(f"{here}?repeat=1", exc.message)
    return _back(here)


@router.post("/issues/{issue_id}/series")
def update_issue_series(
    session: SessionDep,
    chrome: ChromeDep,
    issue_id: int,
    scope: Annotated[EditScope, Form()] = EditScope.THIS,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    priority: Annotated[IssuePriority, Form()] = INITIAL_PRIORITY,
    spawn_mode: Annotated[SeriesSpawnMode, Form()] = SeriesSpawnMode.CALENDAR,
    sprint_basis: Annotated[SeriesSprintBasis, Form()] = SeriesSprintBasis.DUE_ON,
    freq: Annotated[RecurrenceFreq, Form()] = RecurrenceFreq.WEEKLY,
    interval: Annotated[str, Form()] = "1",
    starts_on: Annotated[str, Form()] = "",
    weekday: Annotated[list[str] | None, Form()] = None,
    month_day: Annotated[str, Form()] = "",
    nth_week: Annotated[str, Form()] = "",
    month: Annotated[str, Form()] = "",
    look_ahead_n: Annotated[str, Form()] = "1",
    start_offset_days: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    due_offset_days: Annotated[str, Form()] = "",
    due_time: Annotated[str, Form()] = "",
    end_mode: Annotated[str, Form()] = "never",
    ends_on: Annotated[str, Form()] = "",
    occurrence_count: Annotated[str, Form()] = "",
    labels: Annotated[str, Form()] = "",
) -> RedirectResponse:
    here = _issue_here(session, issue_id)
    try:
        series_service.apply_occurrence_edit(
            session,
            issue_id,
            scope,
            title=title,
            description=description,
            priority=priority,
            spawn_mode=spawn_mode,
            sprint_basis=sprint_basis,
            freq=freq,
            interval=_positive_int(interval, "Repeat interval must be at least 1."),
            weekdays=_weekdays(weekday),
            month_day=_optional_int(month_day),
            nth_week=_optional_signed_int(nth_week),
            month=_optional_int(month),
            starts_on=_required_date(starts_on),
            ends_on=_end_date(end_mode, ends_on),
            occurrence_count=_end_count(end_mode, occurrence_count),
            look_ahead_n=_positive_int(look_ahead_n, "Look-ahead must be at least 1."),
            start_offset_days=_optional_offset(start_offset_days),
            start_minute_of_day=_optional_clock(start_time),
            due_offset_days=_optional_offset(due_offset_days),
            due_minute_of_day=_optional_clock(due_time),
            labels=parse_label_names(labels),
            actor_name=_actor_name(chrome),
        )
    except DomainError as exc:
        session.rollback()
        return _back(f"{here}?repeat=1", exc.message)
    return _back(here)


def _schedule_state(
    session: SessionDep,
    series_id: int,
    state: SeriesState,
) -> RedirectResponse:
    series = series_service.get_series(session, series_id)
    project = project_service.get_project(session, series.project_id)
    here = f"/projects/{project.key}/schedules/{series.id}"
    try:
        series_service.set_state(session, series.id, state)
    except DomainError as exc:
        session.rollback()
        return _back(here, exc.message)
    return _back(here)


def _weekdays(raw: list[str] | str | None) -> tuple[int, ...]:
    if raw is None or raw == "":
        return ()
    if isinstance(raw, str):
        return (int(raw),)
    return tuple(int(item) for item in raw if str(item).strip() != "")


def _required_date(raw: str) -> date:
    parsed = sprint_service.parse_date(raw)
    if parsed is None:
        from keel.domain.errors import InvalidSeriesError

        raise InvalidSeriesError("A series needs a start date.")
    return parsed


def _optional_int(raw: str) -> int | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    return int(cleaned)


def _optional_signed_int(raw: str) -> int | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    return int(cleaned)


def _positive_int(raw: str, message: str) -> int:
    from keel.domain.errors import InvalidSeriesError

    cleaned = raw.strip()
    if not cleaned.isdigit() or int(cleaned) < 1:
        raise InvalidSeriesError(message)
    return int(cleaned)


def _optional_offset(raw: str) -> int | None:
    if not raw.strip():
        return None
    return _offset_days(raw)


def _optional_clock(raw: str) -> int | None:
    if not raw.strip():
        return None
    return parse_clock(raw)


def _offset_days(raw: str) -> int:
    from keel.domain.errors import InvalidSeriesError

    cleaned = raw.strip()
    if not cleaned:
        return 0
    try:
        value = int(cleaned)
    except ValueError as exc:
        raise InvalidSeriesError("Day offset could not be read.") from exc
    if value < 0:
        raise InvalidSeriesError("Day offset cannot be negative.")
    return value


def _end_date(end_mode: str, raw: str) -> date | None:
    if end_mode != "on":
        return None
    return sprint_service.parse_date(raw)


def _end_count(end_mode: str, raw: str) -> int | None:
    if end_mode != "count":
        return None
    return _positive_int(raw, "Occurrence count must be at least 1.")


def _parse_cadence(raw: str) -> SprintCadence:
    try:
        return SprintCadence(raw.strip())
    except ValueError as exc:
        raise InvalidSprintCadenceError("That is not a sprint cadence.") from exc


def _parse_cadence_days(raw: str) -> int | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    if not cleaned.isdigit():
        raise InvalidSprintCadenceError(
            "Every N days needs a number of days of at least 1.",
        )
    return int(cleaned)


def _parse_sprint_ahead(raw: str) -> int:
    cleaned = raw.strip()
    if not cleaned:
        return MIN_SPRINT_AHEAD
    if not cleaned.isdigit():
        raise InvalidSprintCadenceError(
            "Sprints in advance must be a whole number from "
            f"{MIN_SPRINT_AHEAD} to {MAX_SPRINT_AHEAD}.",
        )
    return int(cleaned)
