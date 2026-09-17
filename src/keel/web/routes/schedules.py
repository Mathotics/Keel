from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import (
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
    priorities_in_rank_order,
    types_in_hierarchy_order,
)
from keel.domain.errors import NotFoundError
from keel.domain.recurrence import MONTH_NAMES, WEEKDAY_NAMES, parse_weekdays
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/projects")


@router.get("/{key}/schedules", response_class=HTMLResponse)
def schedules_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    tab: str | None = None,
    error: str | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    found = series_service.list_series(session, project.id)
    return get_templates().TemplateResponse(
        request,
        "schedules.html",
        page_context(
            request,
            chrome,
            project=project,
            new_series=tab == "new",
            series_list=found,
            summaries={item.id: series_service.cadence_summary(item) for item in found},
            issue_types=types_in_hierarchy_order(),
            priorities=priorities_in_rank_order(),
            spawn_modes=tuple(SeriesSpawnMode),
            sprint_bases=tuple(SeriesSprintBasis),
            freqs=tuple(RecurrenceFreq),
            weekdays=list(enumerate(WEEKDAY_NAMES)),
            months=list(enumerate(MONTH_NAMES, start=1)),
            issues=issue_service.list_issues(session, project.id),
            users=user_service.list_users(session),
            error=error,
            notice=notice,
        ),
    )


@router.get("/{key}/schedules/{series_id}", response_class=HTMLResponse)
def schedule_detail_page(
    key: str,
    series_id: int,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    series = series_service.get_series(session, series_id)
    if series.project_id != project.id:
        raise NotFoundError(f"No series {series_id} in {project.key}.")
    selected = set(parse_weekdays(series.weekdays))
    return get_templates().TemplateResponse(
        request,
        "schedule_detail.html",
        page_context(
            request,
            chrome,
            project=project,
            series=series,
            summary=series_service.cadence_summary(series),
            issue_types=types_in_hierarchy_order(),
            priorities=priorities_in_rank_order(),
            spawn_modes=tuple(SeriesSpawnMode),
            sprint_bases=tuple(SeriesSprintBasis),
            freqs=tuple(RecurrenceFreq),
            states=tuple(SeriesState),
            weekdays=list(enumerate(WEEKDAY_NAMES)),
            months=list(enumerate(MONTH_NAMES, start=1)),
            selected_weekdays=selected,
            issues=issue_service.list_issues(session, project.id),
            users=user_service.list_users(session),
            error=error,
            notice=notice,
        ),
    )
