from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from keel.domain.errors import DomainError, NotFoundError, PermissionDeniedError


def register_error_handlers(application: FastAPI) -> None:
    async def domain_error(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, DomainError)
        if isinstance(exc, PermissionDeniedError) and not request.url.path.startswith(
            "/api/"
        ):
            from keel.web.forbid import forbidden_response

            return forbidden_response(request)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.as_detail()},
        )

    async def not_found(_request: Request, exc: Exception) -> Response:
        assert isinstance(exc, NotFoundError)
        return JSONResponse(status_code=404, content={"detail": exc.message})

    application.add_exception_handler(DomainError, domain_error)
    application.add_exception_handler(NotFoundError, not_found)
