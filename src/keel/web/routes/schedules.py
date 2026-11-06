import json
from collections.abc import Sequence

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from keel.db.models import User
from keel.domain.enums import (
    IssuePriority,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
    label,
    priorities_in_rank_order,
    types_in_hierarchy_order,
)
from keel.domain.errors import NotFoundError
from keel.domain.recurrence import MONTH_NAMES, WEEKDAY_NAMES, parse_weekdays
from keel.services import labels as label_service
from keel.services import lookup as lookup_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import series_tree
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/projects")


def _items_json(session: Session, series_id: int) -> str:
    rows = series_tree.active_items(session, series_id)
    labels = label_service.names_for_series_items(session, [item.id for item in rows])
    payload = [
        {
            "id": item.id,
            "key": f"id:{item.id}",
            "parent_key": (
                None if item.parent_item_id is None else f"id:{item.parent_item_id}"
            ),
            "title": item.title,
            "description": item.description,
            "type": item.type.value,
            "priority": item.priority.value,
            "labels": labels.get(item.id, []),
            "assignee_id": item.assignee_id,
            "start_offset_days": item.start_offset_days,
            "start_minute_of_day": item.start_minute_of_day,
            "due_offset_days": item.due_offset_days,
            "due_minute_of_day": item.due_minute_of_day,
        }
        for item in rows
    ]
    return json.dumps(payload)


def _items_config(
    issue_types: Sequence[IssueType],
    priorities: Sequence[IssuePriority],
    users: Sequence[User],
) -> dict[str, object]:
    return {
        "types": [{"value": item.value, "label": label(item)} for item in issue_types],
        "priorities": [
            {"value": item.value, "label": label(item)} for item in priorities
        ],
        "users": [{"id": person.id, "name": person.display_name} for person in users],
    }


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
            series_labels={
                item.id: ", ".join(label_service.names_for_series(session, item.id))
                for item in found
            },
            issue_types=types_in_hierarchy_order(),
            priorities=priorities_in_rank_order(),
            spawn_modes=tuple(SeriesSpawnMode),
            sprint_bases=tuple(SeriesSprintBasis),
            freqs=tuple(RecurrenceFreq),
            weekdays=list(enumerate(WEEKDAY_NAMES)),
            months=list(enumerate(MONTH_NAMES, start=1)),
            parent_label="",
            assignee_label="",
            users=user_service.list_users(session),
            items_json="[]",
            items_config=_items_config(
                types_in_hierarchy_order(),
                priorities_in_rank_order(),
                user_service.list_users(session),
            ),
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
            recipe_labels=", ".join(label_service.names_for_series(session, series.id)),
            issue_types=types_in_hierarchy_order(),
            priorities=priorities_in_rank_order(),
            spawn_modes=tuple(SeriesSpawnMode),
            sprint_bases=tuple(SeriesSprintBasis),
            freqs=tuple(RecurrenceFreq),
            states=tuple(SeriesState),
            weekdays=list(enumerate(WEEKDAY_NAMES)),
            months=list(enumerate(MONTH_NAMES, start=1)),
            selected_weekdays=selected,
            parent_label=lookup_service.parent_field_value(
                session,
                series.parent_id,
                project,
            ),
            assignee_label=lookup_service.user_field_value(
                session,
                series.assignee_id,
            ),
            users=user_service.list_users(session),
            items_json=_items_json(session, series.id),
            items_config=_items_config(
                types_in_hierarchy_order(),
                priorities_in_rank_order(),
                user_service.list_users(session),
            ),
            error=error,
            notice=notice,
        ),
    )
