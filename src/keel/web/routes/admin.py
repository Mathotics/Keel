from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.access import Permission
from keel.services.request_log import (
    LOG_PATH,
    RequestLogQuery,
    count_requests,
    list_requests,
    parse_query,
)
from keel.settings import KeelSettings
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.forbid import require_page
from keel.web.paging import DEFAULT_PAGE_SIZE, PagerRequest, one_pager

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
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    denied = require_page(request, chrome, Permission.VIEW_LOG_TRACKER.value)
    if denied is not None:
        return denied
    query = parse_query(
        person=person,
        start=start,
        end=end,
        span=span,
        kind=kind,
        result=result,
        path=path,
    )
    settings = request.app.state.settings
    assert isinstance(settings, KeelSettings)
    total = count_requests(session, query, settings)
    pager = one_pager(
        LOG_PATH,
        PagerRequest(
            label="Requests per page",
            field_id="log-list-size",
            aria_label="Request pages",
            empty="0 requests",
            total=total,
            page=page,
            size=size,
            keep=_keep(query),
        ),
    )
    rows = list_requests(
        session,
        query,
        limit=pager.window.page_size,
        offset=pager.window.offset,
    )
    empty = (
        "No requests yet."
        if total == 0 and not query.narrowed
        else "No requests match."
    )
    return get_templates().TemplateResponse(
        request,
        "request_log.html",
        page_context(
            request,
            chrome,
            rows=rows,
            query=query,
            empty_message=empty,
            pager=pager,
            today_href=_href(query, size=pager.window.page_size, span="today"),
            week_href=_href(query, size=pager.window.page_size, span="7"),
            month_href=_href(query, size=pager.window.page_size, span="30"),
        ),
    )


def _keep(query: RequestLogQuery) -> tuple[tuple[str, str], ...]:
    """Filter fields the pager must carry so turning a page keeps the search."""
    pairs: list[tuple[str, str]] = []
    if query.user_id is not None:
        pairs.append(("person", str(query.user_id)))
    if query.span:
        pairs.append(("span", query.span))
    else:
        if query.start is not None:
            pairs.append(("start", query.start.isoformat()))
        if query.end is not None:
            pairs.append(("end", query.end.isoformat()))
    if query.changes_only:
        pairs.append(("kind", "changes"))
    if query.result != "all":
        pairs.append(("result", query.result))
    if query.path:
        pairs.append(("path", query.path))
    return tuple(pairs)


def _href(query: RequestLogQuery, *, size: int, span: str) -> str:
    """A date shortcut. It keeps the other filters and the page size."""
    values: dict[str, object] = {
        "person": query.user_id if query.user_id is not None else "",
        "span": span,
        "kind": "changes" if query.changes_only else "",
        "result": "" if query.result == "all" else query.result,
        "path": query.path,
        "size": size,
    }
    params = {
        key: str(value)
        for key, value in values.items()
        if value is not None and str(value) != ""
    }
    if not params:
        return LOG_PATH
    return LOG_PATH + "?" + urlencode(params)
