from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.access import Permission
from keel.domain.cadence import MAX_SPRINT_AHEAD
from keel.domain.enums import sprint_cadences_in_menu_order, statuses_in_workflow_order
from keel.services import access as access_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.filters import FilterRequest, filter_request
from keel.web.guards import require_project_key
from keel.web.paging import DEFAULT_PAGE_SIZE, PagerRequest, one_pager, page_rows
from keel.web.routes.pages import _calendar_page, _gantt_page

router = APIRouter(prefix="/projects")


@router.get("", response_class=HTMLResponse)
def project_list(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    visible = access_service.visible_project_ids(
        chrome.access,
        list(project_service.list_projects(session)),
    )
    pager = one_pager(
        "/projects",
        PagerRequest(
            label="Projects per page",
            field_id="project-list-size",
            aria_label="Project pages",
            empty="0 projects",
            total=len(visible),
            page=page,
            size=size,
        ),
    )
    return get_templates().TemplateResponse(
        request,
        "projects.html",
        page_context(
            request,
            chrome,
            projects=page_rows(visible, pager.window),
            pager=pager,
            error=error,
        ),
    )


@router.get("/{key}", response_class=HTMLResponse)
def project_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    counts = issue_service.count_by_status(session, project.id)
    pager = one_pager(
        f"/projects/{project.key}",
        PagerRequest(
            label="Issues per page",
            field_id="project-issue-size",
            aria_label="Issue pages",
            empty="0 issues",
            total=sum(counts.values()),
            page=page,
            size=size,
        ),
    )
    issues = issue_service.list_issues(
        session,
        project.id,
        limit=pager.window.page_size,
        offset=pager.window.offset,
    )
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    return get_templates().TemplateResponse(
        request,
        "project.html",
        page_context(
            request,
            chrome,
            project=project,
            issues=issues,
            names=names,
            counts=counts,
            statuses=statuses_in_workflow_order(),
            cadences=sprint_cadences_in_menu_order(),
            max_sprint_ahead=MAX_SPRINT_AHEAD,
            pager=pager,
            error=error,
            notice=notice,
            can_view_project_access=access_service.holds_project(
                session, chrome.access, project.id, Permission.VIEW_PROJECT_RBAC
            ),
            can_change_settings=access_service.holds_project(
                session,
                chrome.access,
                project.id,
                Permission.CHANGE_PROJECT_SETTINGS,
            ),
            can_delete_project=access_service.may_delete_project(
                session, chrome.access, project.id
            ),
        ),
    )


@router.get(
    "/{key}/issues/new",
    dependencies=[Depends(require_project_key(Permission.CREATE_ISSUES))],
)
def new_issue_page(key: str, error: str | None = None) -> RedirectResponse:
    """Creating happens on /create; keep the old per-project URL working."""
    params = {"project": key}
    if error:
        params["error"] = error
    return RedirectResponse(url=f"/create?{urlencode(params)}", status_code=303)


@router.get("/{key}/calendar", response_class=HTMLResponse)
def project_calendar_page(
    key: str,
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
    """Month, week, or day of one project's issues."""
    project = project_service.get_project_by_key(session, key)
    return _calendar_page(
        request,
        chrome,
        session,
        raw,
        project=project,
        assignee_id=None,
        month=month,
        year=year,
        month_num=month_num,
        view=view,
        week=week,
        day=day,
        day_num=day_num,
        when=when,
        base=f"/projects/{project.key}/calendar",
    )


@router.get("/{key}/gantt", response_class=HTMLResponse)
def project_gantt_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: Annotated[FilterRequest, Depends(filter_request)],
    month: str | None = None,
    year: int | None = None,
    month_num: int | None = None,
    view: str | None = None,
) -> HTMLResponse:
    """Month, quarter, or year of one project's issues."""
    project = project_service.get_project_by_key(session, key)
    return _gantt_page(
        request,
        chrome,
        session,
        raw,
        project=project,
        assignee_id=None,
        month=month,
        year=year,
        month_num=month_num,
        view=view,
        base=f"/projects/{project.key}/gantt",
    )
