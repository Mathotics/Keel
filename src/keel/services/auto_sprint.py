from collections.abc import Generator
from datetime import date

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Project, Sprint
from keel.db.session import session_factory_of
from keel.domain.cadence import (
    MAX_SPRINT_AHEAD,
    MIN_SPRINT_AHEAD,
    following_window_start,
    next_window_start,
    window_end,
    window_name,
)
from keel.domain.enums import SprintCadence, SprintState, label
from keel.domain.errors import InvalidSprintCadenceError
from keel.services import projects as project_service
from keel.services import sprints as sprint_service

POLL_SECONDS = 60


def cadence_label(project: Project) -> str:
    if project.sprint_cadence is SprintCadence.EVERY_N_DAYS:
        days = project.sprint_cadence_days
        return f"Every {days} days"
    return label(project.sprint_cadence)


def apply_cadence(
    session: Session,
    project: Project,
    cadence: SprintCadence,
    n_days: int | None,
    today: date | None = None,
) -> Project:
    """Store cadence. Opening a window happens only while auto-sprint is on."""
    _validate(cadence, n_days)
    project.sprint_cadence = cadence
    if cadence is SprintCadence.EVERY_N_DAYS:
        project.sprint_cadence_days = n_days
    elif n_days is not None:
        project.sprint_cadence_days = n_days
    if cadence is SprintCadence.OFF:
        project.auto_sprint_notice = ""
    session.flush()
    if cadence is not SprintCadence.OFF:
        ensure_open(session, project.id, today)
    return project


def set_ahead(project: Project, ahead: int) -> None:
    project.sprint_ahead = _validate_ahead(ahead)


def ensure_open(
    session: Session,
    project_id: int,
    today: date | None = None,
) -> Sprint | None:
    """Keep one active sprint while auto-sprint is on. No-op when it is off."""
    project = project_service.get_project(session, project_id)
    if project.sprint_cadence is SprintCadence.OFF:
        return None
    today = today or date.today()
    active = sprint_service.active_sprint(session, project.id)
    opened: Sprint
    if active is not None:
        if active.ends_on is None:
            active.ends_on = _end_from(today, project)
            session.flush()
            opened = active
        elif active.ends_on < today:
            opened = _rollover(session, project, active, today)
        else:
            opened = active
    else:
        opened = _open_now(session, project, today, closed_end=None)
    _ensure_ahead(session, project, today)
    return opened


def complete_sprint(
    session: Session,
    sprint_id: int,
    today: date | None = None,
    *,
    actor_name: str | None = None,
) -> sprint_service.SprintCompletion:
    """Complete, then keep a window open when auto-sprint is on."""
    sprint = sprint_service.get_sprint(session, sprint_id)
    project = project_service.get_project(session, sprint.project_id)
    today = today or date.today()
    if (
        project.sprint_cadence is not SprintCadence.OFF
        and sprint.state is SprintState.ACTIVE
    ):
        _prepare_next(session, project, today, closed_end=sprint.ends_on)
    result = sprint_service.complete_sprint(
        session,
        sprint_id,
        actor_name=actor_name,
    )
    if project.sprint_cadence is not SprintCadence.OFF:
        opened = _start_prepared(session, project, today)
        _ensure_ahead(session, project, today)
        _note_rollover(project, result, opened)
    return result


def start_sprint(
    session: Session,
    sprint_id: int,
    today: date | None = None,
) -> Sprint:
    sprint = sprint_service.start_sprint(session, sprint_id)
    project = project_service.get_project(session, sprint.project_id)
    if project.sprint_cadence is SprintCadence.OFF:
        return sprint
    today = today or date.today()
    if sprint.ends_on is None:
        sprint.ends_on = _end_from(today, project)
        session.flush()
    return sprint


def delete_sprint(
    session: Session,
    sprint_id: int,
    today: date | None = None,
) -> None:
    sprint = sprint_service.get_sprint(session, sprint_id)
    project_id = sprint.project_id
    sprint_service.delete_sprint(session, sprint_id)
    ensure_open(session, project_id, today)


def advance_all(session: Session, today: date | None = None) -> None:
    today = today or date.today()
    projects = session.scalars(
        select(Project).where(Project.sprint_cadence != SprintCadence.OFF),
    ).all()
    for project in projects:
        ensure_open(session, project.id, today)
    from keel.services import series as series_service

    series_service.advance_all(session, today)


def get_session(request: Request) -> Generator[Session, None, None]:
    """Request session that catches up auto-sprint before the handler runs."""
    session = session_factory_of(request)()
    try:
        advance_all(session)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _open_now(
    session: Session,
    project: Project,
    today: date,
    closed_end: date | None,
) -> Sprint:
    planned = _prepare_next(session, project, today, closed_end=closed_end)
    started = sprint_service.start_sprint(session, planned.id)
    _note(project, f"Opened {started.name} automatically.")
    return started


def _rollover(
    session: Session,
    project: Project,
    active: Sprint,
    today: date,
) -> Sprint:
    _prepare_next(session, project, today, closed_end=active.ends_on)
    result = sprint_service.complete_sprint(session, active.id)
    opened = _start_prepared(session, project, today)
    _note_rollover(project, result, opened)
    return opened


def _prepare_next(
    session: Session,
    project: Project,
    today: date,
    closed_end: date | None,
) -> Sprint:
    planned = _usable_planned(session, project.id, today)
    if planned is not None:
        _fill_missing_dates(planned, project, today)
        return planned
    start = next_window_start(closed_end, today)
    end = _end_from(start, project)
    return sprint_service.create_sprint(
        session,
        project.id,
        name=window_name(start, end),
        goal="",
        starts_on=start,
        ends_on=end,
    )


def _start_prepared(session: Session, project: Project, today: date) -> Sprint:
    planned = _usable_planned(session, project.id, today)
    if planned is None:
        return _open_now(session, project, today, closed_end=None)
    _fill_missing_dates(planned, project, today)
    return sprint_service.start_sprint(session, planned.id)


def _usable_planned(session: Session, project_id: int, today: date) -> Sprint | None:
    planned = sprint_service.list_sprints(session, project_id, SprintState.PLANNED)
    for sprint in planned:
        if sprint.ends_on is None or sprint.ends_on >= today:
            return sprint
    return None


def _fill_missing_dates(sprint: Sprint, project: Project, today: date) -> None:
    if sprint.starts_on is None:
        sprint.starts_on = today
    if sprint.ends_on is None:
        sprint.ends_on = _end_from(sprint.starts_on, project)


def _end_from(start: date, project: Project) -> date:
    return window_end(start, project.sprint_cadence, project.sprint_cadence_days)


def _ensure_ahead(session: Session, project: Project, today: date) -> None:
    """Keep N usable planned sprints when auto-sprint is on and N is set."""
    if project.sprint_cadence is SprintCadence.OFF or project.sprint_ahead < 1:
        return
    active = sprint_service.active_sprint(session, project.id)
    if active is not None:
        _fill_missing_dates(active, project, today)
    planned = sprint_service.list_sprints(session, project.id, SprintState.PLANNED)
    usable = [
        sprint
        for sprint in planned
        if sprint.ends_on is None or sprint.ends_on >= today
    ]
    anchor = None if active is None else active.ends_on
    for sprint in usable:
        if sprint.starts_on is None or sprint.ends_on is None:
            start = following_window_start(anchor) if anchor is not None else today
            if sprint.starts_on is None:
                sprint.starts_on = start
            if sprint.ends_on is None:
                sprint.ends_on = _end_from(sprint.starts_on, project)
            session.flush()
        if sprint.ends_on is not None and (anchor is None or sprint.ends_on > anchor):
            anchor = sprint.ends_on
    missing = project.sprint_ahead - len(usable)
    for _ in range(max(0, missing)):
        start = following_window_start(anchor) if anchor is not None else today
        end = _end_from(start, project)
        created = sprint_service.create_sprint(
            session,
            project.id,
            name=window_name(start, end),
            goal="",
            starts_on=start,
            ends_on=end,
        )
        anchor = created.ends_on


def _note_rollover(
    project: Project,
    result: sprint_service.SprintCompletion,
    opened: Sprint,
) -> None:
    opened_line = f"Opened {opened.name} automatically."
    count = result.carried_over
    if count == 0:
        _note(project, opened_line)
        return
    noun = "issue" if count == 1 else "issues"
    if result.carried_to_sprint_id is None:
        carried = f"{count} unfinished {noun} returned to the backlog."
    else:
        carried = f"{count} unfinished {noun} moved to {opened.name}."
    _note(project, f"{opened_line} {carried}")


def _note(project: Project, message: str) -> None:
    project.auto_sprint_notice = message


def _validate(cadence: SprintCadence, n_days: int | None) -> None:
    if cadence is SprintCadence.OFF:
        return
    if cadence is SprintCadence.EVERY_N_DAYS:
        window_end(date.today(), cadence, n_days)
        return
    if cadence not in {
        SprintCadence.WEEKLY,
        SprintCadence.TWO_WEEKS,
        SprintCadence.MONTHLY,
    }:
        raise InvalidSprintCadenceError("That is not a sprint cadence.")


def _validate_ahead(ahead: int) -> int:
    if ahead < MIN_SPRINT_AHEAD or ahead > MAX_SPRINT_AHEAD:
        raise InvalidSprintCadenceError(
            "Sprints in advance must be a whole number from "
            f"{MIN_SPRINT_AHEAD} to {MAX_SPRINT_AHEAD}.",
        )
    return ahead
