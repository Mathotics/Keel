from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import (
    INITIAL_PRIORITY,
    IssueStatus,
    IssueType,
    priorities_in_rank_order,
    statuses_in_workflow_order,
    types_in_hierarchy_order,
)
from keel.paths import license_text
from keel.services import calendar as calendar_service
from keel.services import home as home_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.home_layout import (
    EXTRAS,
    HOME_COOKIE,
    TITLES,
    parse_layout,
    section_rows,
)
from keel.web.inbox import INBOX_COOKIE, SECTIONS, encode_toggle, parse_collapsed

router = APIRouter()


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
    month: str | None = None,
    year: int | None = None,
    month_num: int | None = None,
) -> HTMLResponse:
    """Month view of unfinished issues assigned to the acting user."""
    today = date.today()
    first = calendar_service.chosen_month(
        month,
        year=year,
        month_num=month_num,
        today=today,
    )
    if chrome.current_user is None:
        shown = calendar_service.blank_month(first, today=today)
    else:
        shown = calendar_service.month_calendar(
            session,
            chrome.current_user.id,
            month=first,
            today=today,
        )
    return get_templates().TemplateResponse(
        request,
        "calendar.html",
        page_context(request, chrome, calendar=shown),
    )


@router.get("/create", response_class=HTMLResponse)
def create_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    project: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    projects = project_service.list_projects(session)
    chosen = None
    if project:
        chosen = project_service.get_project_by_key(session, project)
    elif len(projects) == 1:
        chosen = projects[0]
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
            issue_types=types_in_hierarchy_order(),
            default_type=IssueType.STORY,
            statuses=statuses_in_workflow_order(),
            default_status=IssueStatus.TODO,
            priorities=priorities_in_rank_order(),
            default_priority=INITIAL_PRIORITY,
            sprints=sprints,
            error=error,
        ),
    )


@router.get("/license", response_class=HTMLResponse)
def license_page(request: Request, chrome: ChromeDep) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "license.html",
        page_context(request, chrome, license_text=license_text()),
    )
