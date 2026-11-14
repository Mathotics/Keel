from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from keel.domain.access import Permission
from keel.domain.enums import (
    EditScope,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    priorities_in_rank_order,
    statuses_in_workflow_order,
    types_in_hierarchy_order,
)
from keel.domain.hierarchy import child_type_of
from keel.domain.recurrence import MONTH_NAMES, WEEKDAY_NAMES, parse_weekdays
from keel.services import access as access_service
from keel.services import comments as comment_service
from keel.services import dependencies as dependency_service
from keel.services import history as history_service
from keel.services import issues as issue_service
from keel.services import labels as label_service
from keel.services import lookup as lookup_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import series_tree
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.guards import require_issue_key
from keel.web.issue_panels import (
    ISSUE_PANELS_COOKIE,
    encode_toggle,
    parse_collapsed,
)
from keel.web.paging import (
    DEFAULT_PAGE_SIZE,
    PagerRequest,
    page_rows,
    table_pagers,
)

router = APIRouter(prefix="/issues")


@router.get(
    "/{key}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_issue_key(Permission.VIEW_ISSUES))],
)
def issue_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    repeat: str | None = None,
    history_page: int = 1,
    history_size: int = DEFAULT_PAGE_SIZE,
    comments_page: int = 1,
    comments_size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    issue = issue_service.get_issue_by_key(session, key)
    project = project_service.get_project(session, issue.project_id)
    issue_key = issue_service.issue_key(issue, project)
    found_history = history_service.list_history(session, issue.id)
    found_comments = _comment_views(session, issue.id)
    history_pager, comments_pager = table_pagers(
        f"/issues/{issue_key}",
        (
            PagerRequest(
                label="Changes per page",
                field_id="history-size",
                aria_label="History pages",
                empty="0 changes",
                total=len(found_history),
                page=history_page,
                size=history_size,
                key="history",
            ),
            PagerRequest(
                label="Comments per page",
                field_id="comment-size",
                aria_label="Comment pages",
                empty="0 comments",
                total=len(found_comments),
                page=comments_page,
                size=comments_size,
                key="comments",
            ),
        ),
    )
    series = None
    series_item = None
    if issue.series_id is not None:
        series = series_service.attached_series(session, issue)
        if series is not None and issue.series_item_id is not None:
            series_item = series_tree.get_item(session, issue.series_item_id)
    collapsed = parse_collapsed(request.cookies.get(ISSUE_PANELS_COOKIE))

    def issue_panel_toggle(key: str) -> str:
        return encode_toggle(collapsed, key)

    return get_templates().TemplateResponse(
        request,
        "issue_detail.html",
        page_context(
            request,
            chrome,
            project=project,
            issue=issue,
            issue_key=issue_key,
            children=issue_service.list_children(session, issue.id),
            issue_labels=label_service.labels_for_issue(session, issue.id),
            label_catalog=label_service.list_labels(session),
            dependencies=dependency_service.list_for_issue(session, issue.id),
            comments=page_rows(found_comments, comments_pager.window),
            comments_pager=comments_pager,
            history=page_rows(found_history, history_pager.window),
            history_pager=history_pager,
            rollup=issue_service.issue_rollup(session, issue.id),
            parent_label=lookup_service.parent_field_value(
                session,
                issue.parent_id,
                project,
            ),
            assignee_label=lookup_service.user_field_value(
                session,
                issue.assignee_id,
            ),
            reporter=_named(session, issue.reporter_id, empty="None"),
            statuses=statuses_in_workflow_order(),
            priorities=priorities_in_rank_order(),
            issue_types=types_in_hierarchy_order(),
            child_type=child_type_of(issue.type),
            sprints=sprint_service.list_assignable_sprints(
                session,
                project.id,
                current_id=issue.sprint_id,
            ),
            series=series,
            series_item=series_item,
            recipe=_recipe_view(series, series_item),
            recipe_labels=(
                ""
                if series is None
                else ", ".join(
                    label_service.names_for_series_item(session, series_item.id)
                    if series_item is not None
                    else label_service.names_for_series(session, series.id)
                )
            ),
            series_summary=(
                None if series is None else series_service.cadence_summary(series)
            ),
            spawn_modes=tuple(SeriesSpawnMode),
            sprint_bases=tuple(SeriesSprintBasis),
            freqs=tuple(RecurrenceFreq),
            edit_scopes=tuple(EditScope),
            users=user_service.list_users(session),
            weekdays=list(enumerate(WEEKDAY_NAMES)),
            months=list(enumerate(MONTH_NAMES, start=1)),
            selected_weekdays=(
                set() if series is None else set(parse_weekdays(series.weekdays))
            ),
            error=error,
            repeat_overlay=repeat == "1",
            collapsed_issue_panels=collapsed,
            issue_panel_toggle=issue_panel_toggle,
            client_key=issue_service.new_client_key(),
            can_edit_issue=access_service.holds_project(
                session, chrome.access, project.id, Permission.EDIT_ISSUES
            ),
            can_update_issue=access_service.holds_project(
                session, chrome.access, project.id, Permission.UPDATE_ISSUES
            ),
            can_delete_issue=access_service.holds_project(
                session, chrome.access, project.id, Permission.DELETE_ISSUES
            ),
            can_create_issue=access_service.holds_project(
                session, chrome.access, project.id, Permission.CREATE_ISSUES
            ),
        ),
    )


@router.get(
    "/{key}/edit",
    dependencies=[Depends(require_issue_key(Permission.VIEW_ISSUES))],
)
def edit_issue_page(key: str) -> RedirectResponse:
    """Editing happens on the issue page; keep old /edit URLs working."""
    return RedirectResponse(url=f"/issues/{key}", status_code=303)


def _recipe_view(series: object, item: object) -> object:
    if series is None or item is None:
        return series
    return SimpleNamespace(
        title=item.title,  # type: ignore[attr-defined]
        description=item.description,  # type: ignore[attr-defined]
        type=item.type,  # type: ignore[attr-defined]
        priority=item.priority,  # type: ignore[attr-defined]
        spawn_mode=series.spawn_mode,  # type: ignore[attr-defined]
        sprint_basis=series.sprint_basis,  # type: ignore[attr-defined]
        look_ahead_n=series.look_ahead_n,  # type: ignore[attr-defined]
        freq=series.freq,  # type: ignore[attr-defined]
        interval=series.interval,  # type: ignore[attr-defined]
        weekdays=series.weekdays,  # type: ignore[attr-defined]
        month_day=series.month_day,  # type: ignore[attr-defined]
        nth_week=series.nth_week,  # type: ignore[attr-defined]
        month=series.month,  # type: ignore[attr-defined]
        starts_on=series.starts_on,  # type: ignore[attr-defined]
        ends_on=series.ends_on,  # type: ignore[attr-defined]
        occurrence_count=series.occurrence_count,  # type: ignore[attr-defined]
        start_offset_days=item.start_offset_days,  # type: ignore[attr-defined]
        start_minute_of_day=item.start_minute_of_day,  # type: ignore[attr-defined]
        due_offset_days=item.due_offset_days,  # type: ignore[attr-defined]
        due_minute_of_day=item.due_minute_of_day,  # type: ignore[attr-defined]
        state=series.state,  # type: ignore[attr-defined]
    )


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
