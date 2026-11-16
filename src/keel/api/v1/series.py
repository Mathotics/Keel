from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.api.v1.guards import require_issue, require_project, require_series
from keel.db.models import Series
from keel.domain.access import Permission
from keel.domain.enums import SeriesState
from keel.domain.errors import InvalidSeriesError
from keel.schemas.series import (
    OccurrenceEdit,
    SeriesCreate,
    SeriesItemRead,
    SeriesItemWrite,
    SeriesRead,
    SeriesUpdate,
)
from keel.services import history as history_service
from keel.services import labels as label_service
from keel.services import series as series_service
from keel.services import series_tree
from keel.services.series_tree import ItemDraft

router = APIRouter(tags=["series"])


@router.get(
    "/projects/{project_id}/series",
    response_model=list[SeriesRead],
    dependencies=[Depends(require_project(Permission.VIEW_SCHEDULES))],
)
def list_series(project_id: int, session: SessionDep) -> list[SeriesRead]:
    return [
        _read(session, item) for item in series_service.list_series(session, project_id)
    ]


@router.post(
    "/projects/{project_id}/series",
    response_model=SeriesRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_project(Permission.CREATE_SCHEDULES))],
)
def create_series(
    project_id: int,
    payload: SeriesCreate,
    session: SessionDep,
    acting_user: ActingUserDep,
) -> SeriesRead:
    series = series_service.create_series(
        session,
        project_id,
        title=payload.title,
        description=payload.description,
        type=payload.type,
        priority=payload.priority,
        spawn_mode=payload.spawn_mode,
        sprint_basis=payload.sprint_basis,
        freq=payload.freq,
        starts_on=payload.starts_on,
        interval=payload.interval,
        weekdays=tuple(payload.weekdays),
        month_day=payload.month_day,
        nth_week=payload.nth_week,
        month=payload.month,
        ends_on=payload.ends_on,
        occurrence_count=payload.occurrence_count,
        look_ahead_n=payload.look_ahead_n,
        start_offset_days=payload.start_offset_days,
        start_minute_of_day=payload.start_minute_of_day,
        due_offset_days=payload.due_offset_days,
        due_minute_of_day=payload.due_minute_of_day,
        parent_id=payload.parent_id,
        assignee_id=payload.assignee_id,
        reporter_id=None if acting_user is None else acting_user.id,
        seed_issue_id=payload.seed_issue_id,
        labels=payload.labels if "labels" in payload.model_fields_set else None,
        items=_drafts(payload.items) if payload.items else None,
    )
    return _read(session, series)


@router.get(
    "/series/{series_id}",
    response_model=SeriesRead,
    dependencies=[Depends(require_series(Permission.VIEW_SCHEDULES))],
)
def read_series(series_id: int, session: SessionDep) -> SeriesRead:
    return _read(session, series_service.get_series(session, series_id))


@router.patch(
    "/series/{series_id}",
    response_model=SeriesRead,
    dependencies=[Depends(require_series(Permission.EDIT_SCHEDULES))],
)
def update_series(
    series_id: int,
    payload: SeriesUpdate,
    session: SessionDep,
) -> SeriesRead:
    if payload.state is not None and len(payload.model_fields_set) == 1:
        return _read(
            session,
            series_service.set_state(session, series_id, payload.state),
        )
    fields = payload.model_fields_set
    kwargs: dict[str, object] = {}
    for name in (
        "title",
        "description",
        "type",
        "priority",
        "spawn_mode",
        "sprint_basis",
        "freq",
        "interval",
        "starts_on",
        "look_ahead_n",
        "start_offset_days",
        "start_minute_of_day",
        "due_offset_days",
        "due_minute_of_day",
    ):
        if name in fields:
            kwargs[name] = getattr(payload, name)
    if "weekdays" in fields:
        kwargs["weekdays"] = tuple(payload.weekdays or ())
    for name in (
        "month_day",
        "nth_week",
        "month",
        "ends_on",
        "occurrence_count",
        "parent_id",
        "assignee_id",
        "labels",
        "items",
    ):
        if name in fields:
            kwargs[name] = getattr(payload, name)
        # explicit null is a clear
    if "labels" in kwargs and kwargs["labels"] is None:
        kwargs["labels"] = []
    if "items" in kwargs:
        kwargs["items"] = _drafts(payload.items or [])
    series = series_service.update_series(session, series_id, **kwargs)  # type: ignore[arg-type]
    if payload.state is not None:
        series = series_service.set_state(session, series_id, payload.state)
    return _read(session, series)


@router.post(
    "/series/{series_id}/pause",
    response_model=SeriesRead,
    dependencies=[Depends(require_series(Permission.EDIT_SCHEDULES))],
)
def pause_series(series_id: int, session: SessionDep) -> SeriesRead:
    return _read(
        session,
        series_service.set_state(session, series_id, SeriesState.PAUSED),
    )


@router.post(
    "/series/{series_id}/resume",
    response_model=SeriesRead,
    dependencies=[Depends(require_series(Permission.EDIT_SCHEDULES))],
)
def resume_series(series_id: int, session: SessionDep) -> SeriesRead:
    return _read(
        session,
        series_service.set_state(session, series_id, SeriesState.ACTIVE),
    )


@router.post(
    "/issues/{issue_id}/series",
    response_model=SeriesRead,
    dependencies=[Depends(require_issue(Permission.EDIT_SCHEDULES))],
)
def edit_occurrence(
    issue_id: int,
    payload: OccurrenceEdit,
    session: SessionDep,
    acting_user: ActingUserDep,
) -> SeriesRead:
    supplied = payload.model_fields_set
    kwargs: dict[str, object] = {}
    for name in (
        "title",
        "description",
        "priority",
        "spawn_mode",
        "sprint_basis",
        "freq",
        "interval",
        "month_day",
        "nth_week",
        "month",
        "starts_on",
        "ends_on",
        "occurrence_count",
        "look_ahead_n",
        "start_offset_days",
        "start_minute_of_day",
        "due_offset_days",
        "due_minute_of_day",
        "labels",
    ):
        if name in supplied:
            kwargs[name] = getattr(payload, name)
    if "item_action" in supplied:
        kwargs["item_action"] = payload.item_action
    if "item" in supplied and payload.item is not None:
        kwargs["item"] = _drafts([payload.item])[0]
    if "weekdays" in supplied:
        kwargs["weekdays"] = tuple(payload.weekdays or ())
    actor_name = (
        history_service.SYSTEM_ACTOR
        if acting_user is None
        else acting_user.display_name
    )
    issue = series_service.apply_occurrence_edit(
        session,
        issue_id,
        payload.scope,
        actor_name=actor_name,
        **kwargs,  # type: ignore[arg-type]
    )
    if issue.series_id is None:
        raise InvalidSeriesError("This issue is not part of a series.")
    return _read(session, series_service.get_series(session, issue.series_id))


@router.delete(
    "/series/{series_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_series(Permission.DELETE_SCHEDULES))],
)
def delete_series(series_id: int, session: SessionDep) -> None:
    series_service.delete_series(session, series_id)


def _read(session: Session, series: Series) -> SeriesRead:
    return SeriesRead.of(
        series,
        label_service.names_for_series(session, series.id),
        _item_reads(session, series.id),
    )


def _drafts(items: list[SeriesItemWrite]) -> list[ItemDraft]:
    return [
        ItemDraft(
            title=item.title,
            type=item.type,
            description=item.description,
            priority=item.priority,
            assignee_id=item.assignee_id,
            labels=tuple(item.labels),
            start_offset_days=item.start_offset_days,
            start_minute_of_day=item.start_minute_of_day,
            due_offset_days=item.due_offset_days,
            due_minute_of_day=item.due_minute_of_day,
            item_id=item.id,
            key=item.key,
            parent_key=item.parent_key,
        )
        for item in items
    ]


def _item_reads(session: Session, series_id: int) -> list[SeriesItemRead]:
    rows = series_tree.active_items(session, series_id)
    labels = label_service.names_for_series_items(session, [item.id for item in rows])
    return [
        SeriesItemRead(
            id=item.id,
            parent_item_id=item.parent_item_id,
            title=item.title,
            description=item.description,
            type=item.type,
            priority=item.priority,
            assignee_id=item.assignee_id,
            labels=labels.get(item.id, []),
            start_offset_days=item.start_offset_days,
            start_minute_of_day=item.start_minute_of_day,
            due_offset_days=item.due_offset_days,
            due_minute_of_day=item.due_minute_of_day,
        )
        for item in rows
    ]
