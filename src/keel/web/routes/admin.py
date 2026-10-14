from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.services.request_log import (
    LOG_PATH,
    RequestLogQuery,
    list_requests,
    parse_query,
)
from keel.settings import KeelSettings
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter()


@router.get(LOG_PATH, response_class=HTMLResponse)
def request_log_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    person: str | None = None,
    start: str | None = None,
    end: str | None = None,
    span: str | None = None,
    kind: str | None = None,
    result: str | None = None,
    path: str | None = None,
    page: str | None = None,
) -> HTMLResponse:
    query = parse_query(
        person=person,
        start=start,
        end=end,
        span=span,
        kind=kind,
        result=result,
        path=path,
        page=page,
    )
    settings = request.app.state.settings
    assert isinstance(settings, KeelSettings)
    listed = list_requests(session, query, settings)
    shown = RequestLogQuery(
        user_id=query.user_id,
        start=query.start,
        end=query.end,
        span=query.span,
        changes_only=query.changes_only,
        result=query.result,
        path=query.path,
        page=listed.page,
    )
    empty = (
        "No requests yet."
        if listed.total == 0 and not query.narrowed
        else "No requests match."
    )
    return get_templates().TemplateResponse(
        request,
        "request_log.html",
        page_context(
            request,
            chrome,
            rows=listed.rows,
            query=shown,
            empty_message=empty,
            has_older=listed.has_older,
            has_newer=listed.has_newer,
            today_href=_href(shown, span="today", page=None),
            week_href=_href(shown, span="7", page=None),
            month_href=_href(shown, span="30", page=None),
            older_href=_href(shown, page=shown.page + 1),
            newer_href=_href(shown, page=shown.page - 1),
        ),
    )


def _href(query: RequestLogQuery, **overrides: object) -> str:
    values: dict[str, object] = {
        "person": query.user_id if query.user_id is not None else "",
        "start": query.start.isoformat() if query.start else "",
        "end": query.end.isoformat() if query.end else "",
        "span": query.span,
        "kind": "changes" if query.changes_only else "all",
        "result": query.result,
        "path": query.path,
        "page": query.page if query.page > 1 else "",
    }
    values.update(overrides)
    if overrides.get("span"):
        values["start"] = ""
        values["end"] = ""
    params = {
        key: str(value)
        for key, value in values.items()
        if value is not None and str(value) != ""
    }
    if not params:
        return LOG_PATH
    return LOG_PATH + "?" + urlencode(params)
