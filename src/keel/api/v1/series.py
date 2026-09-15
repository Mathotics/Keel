from fastapi import APIRouter, status

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.domain.enums import SeriesState
from keel.schemas.series import SeriesCreate, SeriesRead, SeriesUpdate
from keel.services import series as series_service

router = APIRouter(tags=["series"])


@router.get("/projects/{project_id}/series", response_model=list[SeriesRead])
def list_series(project_id: int, session: SessionDep) -> list[SeriesRead]:
    return [
        SeriesRead.of(item) for item in series_service.list_series(session, project_id)
    ]


@router.post(
    "/projects/{project_id}/series",
    response_model=SeriesRead,
    status_code=status.HTTP_201_CREATED,
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
    )
    return SeriesRead.of(series)


@router.get("/series/{series_id}", response_model=SeriesRead)
def read_series(series_id: int, session: SessionDep) -> SeriesRead:
    return SeriesRead.of(series_service.get_series(session, series_id))


@router.patch("/series/{series_id}", response_model=SeriesRead)
def update_series(
    series_id: int,
    payload: SeriesUpdate,
    session: SessionDep,
) -> SeriesRead:
    if payload.state is not None and len(payload.model_fields_set) == 1:
        return SeriesRead.of(
            series_service.set_state(session, series_id, payload.state),
        )
    fields = payload.model_fields_set
    kwargs: dict[str, object] = {}
    for name in (
        "title",
        "description",
        "type",
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
    ):
        if name in fields:
            kwargs[name] = getattr(payload, name)
        # explicit null is a clear
    series = series_service.update_series(session, series_id, **kwargs)  # type: ignore[arg-type]
    if payload.state is not None:
        series = series_service.set_state(session, series_id, payload.state)
    return SeriesRead.of(series)


@router.post("/series/{series_id}/pause", response_model=SeriesRead)
def pause_series(series_id: int, session: SessionDep) -> SeriesRead:
    return SeriesRead.of(
        series_service.set_state(session, series_id, SeriesState.PAUSED),
    )


@router.post("/series/{series_id}/resume", response_model=SeriesRead)
def resume_series(series_id: int, session: SessionDep) -> SeriesRead:
    return SeriesRead.of(
        series_service.set_state(session, series_id, SeriesState.ACTIVE),
    )


@router.delete("/series/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(series_id: int, session: SessionDep) -> None:
    series_service.delete_series(session, series_id)
