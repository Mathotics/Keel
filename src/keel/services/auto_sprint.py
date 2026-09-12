from collections.abc import Generator
from datetime import date

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Project, Sprint
from keel.db.session import session_factory_of
from keel.domain.cadence import next_window_start, window_end, window_name
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
    if active is not None:
        if active.ends_on is None:
            active.ends_on = _end_from(today, project)
            session.flush()
            return active
        if active.ends_on < today:
            return _rollover(session, project, active, today)
        return active
    return _open_now(session, project, today, closed_end=None)


def complete_sprint(
    session: Session,
    sprint_id: int,
    today: date | None = None,
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
    result = sprint_service.complete_sprint(session, sprint_id)
    if project.sprint_cadence is not SprintCadence.OFF:
        opened = _start_prepared(session, project, today)
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
    planned = sprint_service.next_planned_sprint(session, project.id)
    if planned is None:
        return _open_now(session, project, today, closed_end=None)
    if planned.ends_on is not None and planned.ends_on < today:
        return _open_now(session, project, today, closed_end=None)
    _fill_missing_dates(planned, project, today)
    return sprint_service.start_sprint(session, planned.id)


def _usable_planned(session: Session, project_id: int, today: date) -> Sprint | None:
    planned = sprint_service.next_planned_sprint(session, project_id)
    if planned is None:
        return None
    if planned.ends_on is not None and planned.ends_on < today:
        return None
    return planned


def _fill_missing_dates(sprint: Sprint, project: Project, today: date) -> None:
    if sprint.starts_on is None:
        sprint.starts_on = today
    if sprint.ends_on is None:
        sprint.ends_on = _end_from(sprint.starts_on, project)


def _end_from(start: date, project: Project) -> date:
    return window_end(start, project.sprint_cadence, project.sprint_cadence_days)


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
