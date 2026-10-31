from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from keel.db.models import Project
from keel.domain.enums import (
    INITIAL_PRIORITY,
    IssuePriority,
    IssueStatus,
    IssueType,
    priorities_in_rank_order,
    statuses_in_workflow_order,
    types_in_hierarchy_order,
)
from keel.paths import license_text
from keel.services import calendar as calendar_service
from keel.services import gantt as gantt_service
from keel.services import home as home_service
from keel.services import lookup as lookup_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.filters import (
    FilterRequest,
    date_pairs,
    filter_context,
    filter_request,
    read_bar,
    sprint_menu,
)
from keel.web.home_layout import (
    EXTRAS,
    HOME_COOKIE,
    TITLES,
    parse_layout,
    section_rows,
)
from keel.web.inbox import INBOX_COOKIE, SECTIONS, encode_toggle, parse_collapsed

router = APIRouter()


@dataclass(frozen=True)
class IssueDraft:
    """Create-form values kept when Assign to me redisplays the page."""

    type: IssueType = IssueType.STORY
    title: str = ""
    description: str = ""
    definition_of_done: str = ""
    status: IssueStatus = IssueStatus.TODO
    priority: IssuePriority = INITIAL_PRIORITY
    parent_label: str = ""
    assignee_label: str = ""
    sprint_id: str = ""
    start_at: str = ""
    due_at: str = ""
    estimate: str = ""
    remaining: str = ""
    labels: str = ""


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    """Personal inbox for the acting user; `/projects` stays the directory."""
    inbox = home_service.HomeInbox()
    if chrome.current_user is not None:
        inbox = home_service.personal_inbox(session, chrome.current_user.id)
    collapsed = parse_collapsed(request.cookies.get(INBOX_COOKIE))
    layout = parse_layout(request.cookies.get(HOME_COOKIE))
    panels = []
    for key in layout.order:
        if key in layout.hidden:
            continue
        rows = section_rows(inbox, key)
        if rows:
            panels.append((key, TITLES[key], rows, EXTRAS[key]))

    def inbox_toggle(key: str) -> str:
        return encode_toggle(collapsed, key)

    return get_templates().TemplateResponse(
        request,
        "home.html",
        page_context(
            request,
            chrome,
            inbox=inbox,
            has_projects=bool(project_service.list_projects(session)),
            statuses=statuses_in_workflow_order(),
            collapsed_inbox=collapsed,
            inbox_toggle=inbox_toggle,
            home_panels=panels,
            home_hidden=[
                (key, TITLES[key]) for key in SECTIONS if key in layout.hidden
            ],
            home_visible=",".join(key for key, _title, _rows, _extra in panels),
            error=error,
        ),
    )


@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: Annotated[FilterRequest, Depends(filter_request)],
    month: str | None = None,
    year: int | None = None,
    month_num: int | None = None,
    view: str | None = None,
    week: str | None = None,
    day: str | None = None,
    day_num: int | None = None,
    when: str | None = None,
) -> HTMLResponse:
    """Month, week, or day of issues assigned to the acting user."""
    return _calendar_page(
        request,
        chrome,
        session,
        raw,
        project=None,
        assignee_id=None if chrome.current_user is None else chrome.current_user.id,
        month=month,
        year=year,
        month_num=month_num,
        view=view,
        week=week,
        day=day,
        day_num=day_num,
        when=when,
        base="/calendar",
    )


def _calendar_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: FilterRequest,
    *,
    project: Project | None,
    assignee_id: int | None,
    month: str | None,
    year: int | None,
    month_num: int | None,
    view: str | None,
    week: str | None,
    day: str | None,
    day_num: int | None,
    when: str | None,
    base: str,
) -> HTMLResponse:
    mode = calendar_service.parse_mode(when)
    kept = tuple(pair for pair in date_pairs(request) if pair[0] != "when")
    if mode != "start":
        kept = (*kept, ("when", mode))
    bar = read_bar(
        session,
        raw,
        base=base,
        include_projects=project is None,
        extra=kept,
    )
    shown = calendar_service.open_calendar(
        session,
        assignee_id,
        view=view,
        month=month,
        week=week,
        day=day,
        year=year,
        month_num=month_num,
        day_num=day_num,
        today=date.today(),
        project_id=None if project is None else project.id,
        base=base,
        filters=bar.criteria,
        mode=mode,
    )
    projects = list(project_service.list_projects(session))
    scope = None if project is None else project.id
    return get_templates().TemplateResponse(
        request,
        "calendar.html",
        page_context(
            request,
            chrome,
            project=project,
            calendar=shown,
            **filter_context(
                bar,
                action=base,
                show_project=project is None,
                show_layout=False,
                sprints=sprint_menu(
                    session,
                    project_id=scope,
                    project_ids=bar.criteria.project_ids,
                ),
                project_keys={item.id: item.key for item in projects},
                prefix=project is None,
                separate=False,
                preserve=kept,
                error=None,
            ),
        ),
    )


@router.get("/gantt", response_class=HTMLResponse)
def gantt_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: Annotated[FilterRequest, Depends(filter_request)],
    month: str | None = None,
    year: int | None = None,
    month_num: int | None = None,
    view: str | None = None,
) -> HTMLResponse:
    """Month, quarter, or year of issues assigned to the acting user."""
    return _gantt_page(
        request,
        chrome,
        session,
        raw,
        project=None,
        assignee_id=None if chrome.current_user is None else chrome.current_user.id,
        month=month,
        year=year,
        month_num=month_num,
        view=view,
        base="/gantt",
    )


def _gantt_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: FilterRequest,
    *,
    project: Project | None,
    assignee_id: int | None,
    month: str | None,
    year: int | None,
    month_num: int | None,
    view: str | None,
    base: str,
) -> HTMLResponse:
    kept = _gantt_kept(request)
    bar = read_bar(
        session,
        raw,
        base=base,
        include_projects=project is None,
        extra=kept,
    )
    shown = gantt_service.open_gantt(
        session,
        assignee_id,
        view=view,
        month=month,
        year=year,
        month_num=month_num,
        today=date.today(),
        project_id=None if project is None else project.id,
        base=base,
        filters=bar.criteria,
    )
    projects = list(project_service.list_projects(session))
    scope = None if project is None else project.id
    return get_templates().TemplateResponse(
        request,
        "gantt.html",
        page_context(
            request,
            chrome,
            project=project,
            gantt=shown,
            **filter_context(
                bar,
                action=base,
                show_project=project is None,
                show_layout=False,
                sprints=sprint_menu(
                    session,
                    project_id=scope,
                    project_ids=bar.criteria.project_ids,
                ),
                project_keys={item.id: item.key for item in projects},
                prefix=project is None,
                separate=False,
                preserve=kept,
                error=None,
            ),
        ),
    )


def _gantt_kept(request: Request) -> tuple[tuple[str, str], ...]:
    """Keep the gantt scale and dropdowns. Other date params belong to the calendar."""
    kept: list[tuple[str, str]] = []
    for key, value in date_pairs(request):
        if key not in {"view", "month", "year", "month_num"}:
            continue
        if key == "view" and value not in {"quarter", "year"}:
            continue
        kept.append((key, value))
    return tuple(kept)


def render_create_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    *,
    project: str | None = None,
    error: str | None = None,
    draft: IssueDraft | None = None,
) -> HTMLResponse:
    filled = draft or IssueDraft()
    projects = project_service.list_projects(session)
    chosen = None
    project_label = ""
    project_error = None
    if project and project.strip():
        chosen, project_label, project_error = lookup_service.interpret_project(
            session,
            project,
        )
    elif len(projects) == 1:
        chosen = projects[0]
        project_label = lookup_service.project_field_value(chosen)
    sprints = []
    if chosen is not None:
        sprints = list(sprint_service.list_assignable_sprints(session, chosen.id))
    return get_templates().TemplateResponse(
        request,
        "create.html",
        page_context(
            request,
            chrome,
            projects=projects,
            project=chosen,
            project_label=project_label,
            error=error or project_error,
            issue_types=types_in_hierarchy_order(),
            default_type=filled.type,
            statuses=statuses_in_workflow_order(),
            default_status=filled.status,
            priorities=priorities_in_rank_order(),
            default_priority=filled.priority,
            sprints=sprints,
            draft=filled,
        ),
    )


@router.get("/create", response_class=HTMLResponse)
def create_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    project: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    return render_create_page(
        request,
        chrome,
        session,
        project=project,
        error=error,
    )


@router.get("/license", response_class=HTMLResponse)
def license_page(request: Request, chrome: ChromeDep) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "license.html",
        page_context(request, chrome, license_text=license_text()),
    )
