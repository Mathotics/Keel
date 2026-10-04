from fastapi import APIRouter
from fastapi.responses import JSONResponse

from keel.services import lookup as lookup_service
from keel.web.context import SessionDep

router = APIRouter(prefix="/web")


@router.get("/lookup/issues")
def lookup_issues(
    session: SessionDep,
    q: str = "",
    project: str | None = None,
    exclude: int | None = None,
) -> JSONResponse:
    project_id = lookup_service.project_id_for_key(session, project)
    if project and project.strip() and project_id is None:
        return JSONResponse([])
    hits = lookup_service.suggest_issues(
        session,
        q,
        project_id=project_id,
        exclude_id=exclude,
    )
    return JSONResponse(
        [{"id": hit.id, "key": hit.key, "title": hit.title} for hit in hits],
    )


@router.get("/lookup/labels")
def lookup_labels(session: SessionDep, q: str = "") -> JSONResponse:
    return JSONResponse(lookup_service.suggest_labels(session, q))


@router.get("/lookup/users")
def lookup_users(session: SessionDep, q: str = "") -> JSONResponse:
    hits = lookup_service.suggest_users(session, q)
    return JSONResponse([{"id": hit.id, "label": hit.label} for hit in hits])


@router.get("/lookup/projects")
def lookup_projects(session: SessionDep, q: str = "") -> JSONResponse:
    hits = lookup_service.suggest_projects(session, q)
    return JSONResponse(
        [{"id": hit.id, "key": hit.key, "name": hit.name} for hit in hits],
    )
