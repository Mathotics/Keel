from fastapi import APIRouter
from fastapi.responses import JSONResponse

from keel.domain.access import Permission
from keel.services import access as access_service
from keel.services import lookup as lookup_service
from keel.web.context import ChromeDep, SessionDep

router = APIRouter(prefix="/web")


@router.get("/lookup/issues")
def lookup_issues(
    session: SessionDep,
    chrome: ChromeDep,
    q: str = "",
    project: str | None = None,
    exclude: int | None = None,
) -> JSONResponse:
    allowed = access_service.project_ids_holding(
        session, chrome.access, Permission.VIEW_ISSUES
    )
    project_id = lookup_service.project_id_for_key(session, project)
    if project and project.strip() and project_id is None:
        return JSONResponse([])
    if project_id is not None and allowed is not None and project_id not in allowed:
        return JSONResponse([])
    hits = lookup_service.suggest_issues(
        session,
        q,
        project_id=project_id,
        exclude_id=exclude,
        allowed=allowed,
    )
    return JSONResponse(
        [{"id": hit.id, "key": hit.key, "title": hit.title} for hit in hits],
    )


@router.get("/lookup/labels")
def lookup_labels(session: SessionDep, chrome: ChromeDep, q: str = "") -> JSONResponse:
    allowed = access_service.label_project_ids(session, chrome.access)
    return JSONResponse(lookup_service.suggest_labels(session, q, allowed=allowed))


@router.get("/lookup/users")
def lookup_users(
    session: SessionDep,
    q: str = "",
    empty: str = "",
) -> JSONResponse:
    hits = lookup_service.suggest_users(
        session,
        q,
        empty="none" if empty == "none" else "unassigned",
    )
    return JSONResponse([{"id": hit.id, "label": hit.label} for hit in hits])


@router.get("/lookup/projects")
def lookup_projects(
    session: SessionDep,
    chrome: ChromeDep,
    q: str = "",
) -> JSONResponse:
    allowed = access_service.project_ids_holding(
        session, chrome.access, Permission.VIEW_ISSUES
    )
    hits = lookup_service.suggest_projects(session, q, allowed=allowed)
    return JSONResponse(
        [{"id": hit.id, "key": hit.key, "name": hit.name} for hit in hits],
    )
