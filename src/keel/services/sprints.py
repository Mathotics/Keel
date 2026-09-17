from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project, Sprint
from keel.db.models.user import utc_now
from keel.domain.enums import CLOSED_STATUSES, SprintState
from keel.domain.errors import (
    InvalidSprintError,
    NotFoundError,
    SprintAlreadyActiveError,
    SprintInvalidTransitionError,
)
from keel.services import projects as project_service

MAX_NAME_LENGTH = 200
UNSET = object()


@dataclass(frozen=True)
class SprintCompletion:
    sprint: Sprint
    carried_over: int
    carried_to_sprint_id: int | None


def list_sprints(
    session: Session,
    project_id: int,
    state: SprintState | None = None,
) -> Sequence[Sprint]:
    project_service.get_project(session, project_id)
    query = select(Sprint).where(Sprint.project_id == project_id)
    if state is not None:
        query = query.where(Sprint.state == state)
    return session.scalars(
        query.order_by(Sprint.starts_on.asc().nulls_last(), Sprint.id),
    ).all()


def list_all_sprints(session: Session) -> Sequence[Sprint]:
    """Every sprint, ordered by project key then the usual sprint order."""
    return session.scalars(
        select(Sprint)
        .join(Project, Sprint.project_id == Project.id)
        .order_by(Project.key, Sprint.starts_on.asc().nulls_last(), Sprint.id),
    ).all()


def get_sprint(session: Session, sprint_id: int) -> Sprint:
    sprint = session.get(Sprint, sprint_id)
    if sprint is None:
        raise NotFoundError(f"No sprint with id {sprint_id}.")
    return sprint


def list_sprint_issues(session: Session, sprint_id: int) -> Sequence[Issue]:
    sprint = get_sprint(session, sprint_id)
    return session.scalars(
        select(Issue).where(Issue.sprint_id == sprint.id).order_by(Issue.number),
    ).all()


def create_sprint(
    session: Session,
    project_id: int,
    name: str,
    goal: str = "",
    starts_on: date | None = None,
    ends_on: date | None = None,
) -> Sprint:
    project = project_service.get_project(session, project_id)
    _check_dates(starts_on, ends_on)
    sprint = Sprint(
        project_id=project.id,
        name=_clean_name(name),
        goal=goal.strip(),
        state=SprintState.PLANNED,
        starts_on=starts_on,
        ends_on=ends_on,
    )
    session.add(sprint)
    session.flush()
    return sprint


def update_sprint(
    session: Session,
    sprint_id: int,
    *,
    name: str | None = None,
    goal: str | None = None,
    starts_on: date | None | object = UNSET,
    ends_on: date | None | object = UNSET,
) -> Sprint:
    """Nullable dates accept None as "clear it", so they use UNSET."""
    sprint = get_sprint(session, sprint_id)
    if name is not None:
        sprint.name = _clean_name(name)
    if goal is not None:
        sprint.goal = goal.strip()
    next_start = sprint.starts_on if starts_on is UNSET else starts_on
    next_end = sprint.ends_on if ends_on is UNSET else ends_on
    _check_dates(next_start, next_end)  # type: ignore[arg-type]
    if starts_on is not UNSET:
        sprint.starts_on = starts_on  # type: ignore[assignment]
    if ends_on is not UNSET:
        sprint.ends_on = ends_on  # type: ignore[assignment]
    session.flush()
    return sprint


def delete_sprint(session: Session, sprint_id: int) -> None:
    """Issues are unscheduled by the foreign key, not deleted."""
    session.delete(get_sprint(session, sprint_id))
    session.flush()


def next_planned_sprint(session: Session, project_id: int) -> Sprint | None:
    return _next_planned(session, project_id)


def active_sprint(session: Session, project_id: int) -> Sprint | None:
    return session.scalars(
        select(Sprint).where(
            Sprint.project_id == project_id,
            Sprint.state == SprintState.ACTIVE,
        ),
    ).first()


def start_sprint(session: Session, sprint_id: int) -> Sprint:
    sprint = get_sprint(session, sprint_id)
    if sprint.state is not SprintState.PLANNED:
        raise SprintInvalidTransitionError(
            "Only a planned sprint can be started.",
            sprint_id=sprint.id,
            state=sprint.state.value,
        )
    already = session.scalars(
        select(Sprint).where(
            Sprint.project_id == sprint.project_id,
            Sprint.state == SprintState.ACTIVE,
        ),
    ).first()
    if already is not None:
        raise SprintAlreadyActiveError(
            "This project already has an active sprint.",
            sprint_id=sprint.id,
            active_sprint_id=already.id,
        )
    sprint.state = SprintState.ACTIVE
    session.flush()
    return sprint


def complete_sprint(
    session: Session,
    sprint_id: int,
    *,
    actor_name: str | None = None,
) -> SprintCompletion:
    from keel.services import history as history_service

    sprint = get_sprint(session, sprint_id)
    if sprint.state is not SprintState.ACTIVE:
        raise SprintInvalidTransitionError(
            "Only an active sprint can be completed.",
            sprint_id=sprint.id,
            state=sprint.state.value,
        )
    unfinished = session.scalars(
        select(Issue).where(
            Issue.sprint_id == sprint.id,
            Issue.status.notin_(CLOSED_STATUSES),
        ),
    ).all()
    destination = _next_planned(session, sprint.project_id)
    dest_id = None if destination is None else destination.id
    who = actor_name if actor_name is not None else history_service.current_actor_name()
    for issue in unfinished:
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_SPRINT,
            from_value=history_service.sprint_label(session, issue.sprint_id),
            to_value=history_service.sprint_label(session, dest_id),
            actor_name=who,
        )
        issue.sprint_id = dest_id
    sprint.state = SprintState.COMPLETED
    sprint.completed_at = utc_now()
    session.flush()
    return SprintCompletion(
        sprint=sprint,
        carried_over=len(unfinished),
        carried_to_sprint_id=dest_id,
    )


def parse_date(raw: str) -> date | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise InvalidSprintError("A sprint date could not be read.") from exc


def _next_planned(session: Session, project_id: int) -> Sprint | None:
    return session.scalars(
        select(Sprint)
        .where(
            Sprint.project_id == project_id,
            Sprint.state == SprintState.PLANNED,
        )
        .order_by(Sprint.starts_on.asc().nulls_last(), Sprint.id),
    ).first()


def _check_dates(starts_on: date | None, ends_on: date | None) -> None:
    if starts_on is not None and ends_on is not None and ends_on < starts_on:
        raise InvalidSprintError("A sprint cannot end before it starts.")


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidSprintError("A sprint needs a name.")
    return cleaned[:MAX_NAME_LENGTH]
