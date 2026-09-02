from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.responses import Response

from keel.db.models import Project
from keel.domain.errors import NotFoundError
from keel.services import find as find_service
from keel.services import projects as project_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter()
EMPTY_QUERY = 302


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    q: str = "",
    project: str | None = None,
) -> Response:
    needle = q.strip()
    if not needle:
        return RedirectResponse(url="/projects", status_code=EMPTY_QUERY)
    scoped = _resolve_project(session, project)
    outcome = find_service.find(
        session,
        needle,
        None if scoped is None else scoped.id,
    )
    if isinstance(outcome, find_service.FindJump):
        return RedirectResponse(url=outcome.url, status_code=303)
    return get_templates().TemplateResponse(
        request,
        "search.html",
        page_context(
            request,
            chrome,
            project=scoped,
            find_query=outcome.query,
            results=outcome,
            scoped=scoped is not None,
        ),
    )


def _resolve_project(session: Session, key: str | None) -> Project | None:
    if not key:
        return None
    try:
        return project_service.get_project_by_key(session, key)
    except NotFoundError:
        return None
