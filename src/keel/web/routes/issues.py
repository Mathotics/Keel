from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/issues")


@router.get("/{key}", response_class=HTMLResponse)
def issue_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    issue = issue_service.get_issue_by_key(session, key)
    project = project_service.get_project(session, issue.project_id)
    parent = (
        None
        if issue.parent_id is None
        else issue_service.get_issue(
            session,
            issue.parent_id,
        )
    )
    return get_templates().TemplateResponse(
        request,
        "issue_detail.html",
        page_context(
            request,
            chrome,
            project=project,
            issue=issue,
            issue_key=issue_service.issue_key(issue, project),
            parent=parent,
            children=issue_service.list_children(session, issue.id),
            assignee=_named(session, issue.assignee_id, empty="Unassigned"),
            reporter=_named(session, issue.reporter_id, empty="None"),
            error=error,
        ),
    )


@router.get("/{key}/edit", response_class=HTMLResponse)
def edit_issue_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    issue = issue_service.get_issue_by_key(session, key)
    project = project_service.get_project(session, issue.project_id)
    candidates = [
        candidate
        for candidate in issue_service.list_issues(session, project.id)
        if candidate.id != issue.id
    ]
    return get_templates().TemplateResponse(
        request,
        "issue_form.html",
        page_context(
            request,
            chrome,
            project=project,
            issue=issue,
            issue_key=issue_service.issue_key(issue, project),
            parents=candidates,
            assignees=user_service.list_users(session),
            reporter=_named(session, issue.reporter_id, empty="None"),
            error=error,
        ),
    )


def _named(session: Session, user_id: int | None, empty: str) -> str:
    if user_id is None:
        return empty
    return user_service.get_user(session, user_id).display_name
