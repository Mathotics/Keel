from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.responses import Response

from keel.db.models import Project
from keel.domain.errors import NotFoundError
from keel.services import find as find_service
from keel.services import projects as project_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.paging import DEFAULT_PAGE_SIZE, PagerRequest, table_pagers

router = APIRouter()
EMPTY_QUERY = 302


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    q: str = "",
    project: str | None = None,
    issues_page: int = 1,
    issues_size: int = DEFAULT_PAGE_SIZE,
    projects_page: int = 1,
    projects_size: int = DEFAULT_PAGE_SIZE,
    sprints_page: int = 1,
    sprints_size: int = DEFAULT_PAGE_SIZE,
    users_page: int = 1,
    users_size: int = DEFAULT_PAGE_SIZE,
) -> Response:
    needle = q.strip()
    if not needle:
        return RedirectResponse(url="/projects", status_code=EMPTY_QUERY)
    scoped = _resolve_project(session, project)
    project_id = None if scoped is None else scoped.id
    jump = find_service.lookup_jump(session, needle, project_id)
    if jump is not None:
        return RedirectResponse(url=jump.url, status_code=303)
    issue_total, project_total, sprint_total, user_total = find_service.match_totals(
        session,
        needle,
        project_id,
    )
    keep = [("q", needle)]
    if scoped is not None:
        keep.append(("project", scoped.key))
    kept = tuple(keep)
    issues_pager, projects_pager, sprints_pager, users_pager = table_pagers(
        "/search",
        (
            PagerRequest(
                label="Issues per page",
                field_id="find-issue-size",
                aria_label="Issue pages",
                empty="0 issues",
                total=issue_total,
                page=issues_page,
                size=issues_size,
                key="issues",
                keep=kept,
            ),
            PagerRequest(
                label="Projects per page",
                field_id="find-project-size",
                aria_label="Project pages",
                empty="0 projects",
                total=project_total,
                page=projects_page,
                size=projects_size,
                key="projects",
                keep=kept,
            ),
            PagerRequest(
                label="Sprints per page",
                field_id="find-sprint-size",
                aria_label="Sprint pages",
                empty="0 sprints",
                total=sprint_total,
                page=sprints_page,
                size=sprints_size,
                key="sprints",
                keep=kept,
            ),
            PagerRequest(
                label="Users per page",
                field_id="find-user-size",
                aria_label="User pages",
                empty="0 users",
                total=user_total,
                page=users_page,
                size=users_size,
                key="users",
                keep=kept,
            ),
        ),
    )
    results = find_service.FindResults(
        query=needle,
        issues=find_service.load_issue_hits(
            session,
            needle,
            project_id,
            limit=issues_pager.window.page_size,
            offset=issues_pager.window.offset,
        ),
        issues_more=False,
        projects=find_service.load_project_hits(
            session,
            needle,
            limit=projects_pager.window.page_size,
            offset=projects_pager.window.offset,
        ),
        projects_more=False,
        sprints=find_service.load_sprint_hits(
            session,
            needle,
            project_id,
            limit=sprints_pager.window.page_size,
            offset=sprints_pager.window.offset,
        ),
        sprints_more=False,
        users=find_service.load_user_hits(
            session,
            needle,
            limit=users_pager.window.page_size,
            offset=users_pager.window.offset,
        ),
        users_more=False,
    )
    return get_templates().TemplateResponse(
        request,
        "search.html",
        page_context(
            request,
            chrome,
            project=scoped,
            find_query=needle,
            results=results,
            scoped=scoped is not None,
            issues_pager=issues_pager,
            projects_pager=projects_pager,
            sprints_pager=sprints_pager,
            users_pager=users_pager,
        ),
    )


def _resolve_project(session: Session, key: str | None) -> Project | None:
    if not key:
        return None
    try:
        return project_service.get_project_by_key(session, key)
    except NotFoundError:
        return None
