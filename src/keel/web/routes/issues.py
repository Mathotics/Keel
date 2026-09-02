from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from keel.domain.enums import statuses_in_workflow_order, types_in_hierarchy_order
from keel.domain.hierarchy import child_type_of
from keel.services import comments as comment_service
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
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
    projects = {item.id: item for item in project_service.list_projects(session)}
    candidates = [
        {
            "id": other.id,
            "key": issue_service.issue_key(other, projects[other.project_id]),
            "title": other.title,
        }
        for other in issue_service.list_issues_globally(session)
        if other.id != issue.id
    ]
    return get_templates().TemplateResponse(
        request,
        "issue_detail.html",
        page_context(
            request,
            chrome,
            project=project,
            issue=issue,
            issue_key=issue_service.issue_key(issue, project),
            children=issue_service.list_children(session, issue.id),
            dependencies=dependency_service.list_for_issue(session, issue.id),
            comments=_comment_views(session, issue.id),
            rollup=issue_service.issue_rollup(session, issue.id),
            candidates=candidates,
            reporter=_named(session, issue.reporter_id, empty="None"),
            statuses=statuses_in_workflow_order(),
            issue_types=types_in_hierarchy_order(),
            child_type=child_type_of(issue.type),
            parents=[
                candidate
                for candidate in issue_service.list_issues(session, project.id)
                if candidate.id != issue.id
            ],
            sprints=sprint_service.list_sprints(session, project.id),
            error=error,
        ),
    )


@router.get("/{key}/edit")
def edit_issue_page(key: str) -> RedirectResponse:
    """Editing happens on the issue page; keep old /edit URLs working."""
    return RedirectResponse(url=f"/issues/{key}", status_code=303)


def _comment_views(session: Session, issue_id: int) -> list[dict[str, object]]:
    names = {
        person.id: person.display_name for person in user_service.list_users(session)
    }
    return [
        {
            "id": comment.id,
            "body": comment.body,
            "created_at": comment.created_at,
            "author_name": names.get(comment.author_id, "None")
            if comment.author_id is not None
            else "None",
        }
        for comment in comment_service.list_comments(session, issue_id)
    ]


def _named(session: Session, user_id: int | None, empty: str) -> str:
    if user_id is None:
        return empty
    return user_service.get_user(session, user_id).display_name
