from datetime import date

import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project, Sprint
from keel.domain.enums import IssueStatus, IssueType, SprintCadence, SprintState
from keel.domain.errors import InvalidSprintCadenceError
from keel.services import auto_sprint
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service

TODAY = date(2026, 9, 12)


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _issue(session: Session, project: Project, title: str, sprint_id: int) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title=title,
        sprint_id=sprint_id,
    ).id


def test_a_new_project_has_auto_sprint_off(session: Session, project: Project) -> None:
    assert project.sprint_cadence is SprintCadence.OFF
    assert project.sprint_cadence_days is None
    assert project.sprint_ahead == 0


def test_turning_on_with_no_sprint_opens_a_window_from_today(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)

    active = sprint_service.active_sprint(session, project.id)
    assert active is not None
    assert active.state is SprintState.ACTIVE
    assert active.starts_on == TODAY
    assert active.ends_on == date(2026, 9, 18)
    assert active.name == "12 Sep – 18 Sep 2026"
    assert active.goal == ""
    assert "Opened 12 Sep – 18 Sep 2026 automatically." in project.auto_sprint_notice


def test_every_n_days_opens_a_window_of_that_length(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(
        session,
        project,
        SprintCadence.EVERY_N_DAYS,
        5,
        TODAY,
    )
    active = sprint_service.active_sprint(session, project.id)
    assert active is not None
    assert active.ends_on == date(2026, 9, 16)
    assert auto_sprint.cadence_label(project) == "Every 5 days"


def test_a_custom_day_count_is_kept_when_switching_to_a_preset(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(
        session,
        project,
        SprintCadence.WEEKLY,
        8,
        TODAY,
    )
    assert project.sprint_cadence is SprintCadence.WEEKLY
    assert project.sprint_cadence_days == 8


def test_manual_start_while_auto_on_dates_a_missing_end(
    session: Session,
    project: Project,
) -> None:
    planned = sprint_service.create_sprint(session, project.id, "Soon")
    project.sprint_cadence = SprintCadence.WEEKLY
    session.flush()
    started = auto_sprint.start_sprint(session, planned.id, TODAY)
    assert started.state is SprintState.ACTIVE
    assert started.ends_on == date(2026, 9, 18)


def test_turning_on_dates_an_undated_planned_sprint(
    session: Session,
    project: Project,
) -> None:
    planned = sprint_service.create_sprint(session, project.id, "Soon")
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    started = sprint_service.get_sprint(session, planned.id)
    assert started.state is SprintState.ACTIVE
    assert started.starts_on == TODAY
    assert started.ends_on == date(2026, 9, 18)


def test_turning_on_with_an_undated_active_sprint_sets_only_the_end(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        "Now",
        starts_on=date(2026, 9, 1),
    )
    sprint_service.start_sprint(session, sprint.id)

    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)

    updated = sprint_service.get_sprint(session, sprint.id)
    assert updated.state is SprintState.ACTIVE
    assert updated.starts_on == date(2026, 9, 1)
    assert updated.ends_on == date(2026, 9, 18)


def test_turning_on_starts_the_next_planned_sprint(
    session: Session,
    project: Project,
) -> None:
    planned = sprint_service.create_sprint(
        session,
        project.id,
        "Already planned",
        starts_on=date(2026, 9, 14),
        ends_on=date(2026, 9, 27),
    )

    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)

    started = sprint_service.get_sprint(session, planned.id)
    assert started.state is SprintState.ACTIVE
    assert started.starts_on == date(2026, 9, 14)
    assert started.ends_on == date(2026, 9, 27)
    current = sprint_service.active_sprint(session, project.id)
    assert current is not None
    assert current.id == planned.id


def test_changing_cadence_does_not_rewrite_the_current_window(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    active = sprint_service.active_sprint(session, project.id)
    assert active is not None
    original_end = active.ends_on

    auto_sprint.apply_cadence(session, project, SprintCadence.MONTHLY, None, TODAY)

    same = sprint_service.get_sprint(session, active.id)
    assert same.ends_on == original_end
    assert same.state is SprintState.ACTIVE
    assert project.sprint_cadence is SprintCadence.MONTHLY


def test_turning_off_leaves_the_current_sprint(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    active = sprint_service.active_sprint(session, project.id)
    assert active is not None
    active_id = active.id

    auto_sprint.apply_cadence(session, project, SprintCadence.OFF, None, TODAY)

    left = sprint_service.get_sprint(session, active_id)
    assert left.state is SprintState.ACTIVE
    assert project.sprint_cadence is SprintCadence.OFF
    assert auto_sprint.ensure_open(session, project.id, TODAY) is None


def test_every_n_days_requires_a_positive_count(
    session: Session,
    project: Project,
) -> None:
    with pytest.raises(InvalidSprintCadenceError):
        auto_sprint.apply_cadence(
            session,
            project,
            SprintCadence.EVERY_N_DAYS,
            None,
            TODAY,
        )


def test_rollover_happens_the_day_after_the_inclusive_end(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None
    work = _issue(session, project, "Carry me", first.id)

    auto_sprint.advance_all(session, TODAY)
    assert sprint_service.get_sprint(session, first.id).state is SprintState.ACTIVE

    auto_sprint.advance_all(session, date(2026, 9, 18))
    assert sprint_service.get_sprint(session, first.id).state is SprintState.ACTIVE

    auto_sprint.advance_all(session, date(2026, 9, 19))
    closed = sprint_service.get_sprint(session, first.id)
    nxt = sprint_service.active_sprint(session, project.id)
    assert closed.state is SprintState.COMPLETED
    assert nxt is not None
    assert nxt.id != first.id
    assert nxt.starts_on == date(2026, 9, 19)
    assert nxt.ends_on == date(2026, 9, 25)
    assert nxt.name == "19 Sep – 25 Sep 2026"
    assert issue_service.get_issue(session, work).sprint_id == nxt.id
    assert "Opened 19 Sep – 25 Sep 2026 automatically." in project.auto_sprint_notice


def test_rollover_uses_an_existing_planned_sprint(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None
    planned = sprint_service.create_sprint(
        session,
        project.id,
        "Next",
        starts_on=date(2026, 9, 19),
        ends_on=date(2026, 10, 2),
    )

    auto_sprint.advance_all(session, date(2026, 9, 19))

    assert sprint_service.get_sprint(session, first.id).state is SprintState.COMPLETED
    assert sprint_service.get_sprint(session, planned.id).state is SprintState.ACTIVE


def test_catch_up_does_not_create_a_chain_of_empty_sprints(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None

    auto_sprint.advance_all(session, date(2026, 10, 10))

    listed = sprint_service.list_sprints(session, project.id)
    completed = [item for item in listed if item.state is SprintState.COMPLETED]
    active = [item for item in listed if item.state is SprintState.ACTIVE]
    assert [item.id for item in completed] == [first.id]
    assert len(active) == 1
    assert active[0].starts_on == date(2026, 10, 10)
    assert active[0].ends_on == date(2026, 10, 16)


def test_catch_up_skips_a_planned_sprint_that_is_already_past(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None
    stale = sprint_service.create_sprint(
        session,
        project.id,
        "Stale",
        starts_on=date(2026, 9, 19),
        ends_on=date(2026, 9, 25),
    )

    auto_sprint.advance_all(session, date(2026, 10, 10))

    assert sprint_service.get_sprint(session, stale.id).state is SprintState.PLANNED
    current = sprint_service.active_sprint(session, project.id)
    assert current is not None
    assert current.id not in {first.id, stale.id}
    assert current.starts_on == date(2026, 10, 10)


def test_manual_complete_while_auto_on_opens_the_next_window(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None
    work = _issue(session, project, "Still going", first.id)

    result = auto_sprint.complete_sprint(session, first.id, TODAY)

    assert result.sprint.state is SprintState.COMPLETED
    nxt = sprint_service.active_sprint(session, project.id)
    assert nxt is not None
    assert issue_service.get_issue(session, work).sprint_id == nxt.id
    assert nxt.starts_on == TODAY


def test_deleting_the_active_sprint_while_auto_on_opens_another(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None

    auto_sprint.delete_sprint(session, first.id, TODAY)

    nxt = sprint_service.active_sprint(session, project.id)
    assert nxt is not None
    assert nxt.state is SprintState.ACTIVE


def test_manual_complete_with_auto_off_still_returns_work_to_the_backlog(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Now")
    work = _issue(session, project, "Open", current.id)
    sprint_service.start_sprint(session, current.id)
    issue_service.update_issue(session, work, status=IssueStatus.TODO)

    result = auto_sprint.complete_sprint(session, current.id, TODAY)

    assert result.carried_to_sprint_id is None
    assert issue_service.get_issue(session, work).sprint_id is None
    assert sprint_service.active_sprint(session, project.id) is None


def _planned(session: Session, project: Project) -> list[Sprint]:
    return [
        item
        for item in sprint_service.list_sprints(session, project.id)
        if item.state is SprintState.PLANNED
    ]


def test_turning_on_with_ahead_creates_dated_planned_windows(
    session: Session,
    project: Project,
) -> None:
    project.sprint_ahead = 2
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)

    active = sprint_service.active_sprint(session, project.id)
    assert active is not None
    planned = _planned(session, project)
    assert [item.starts_on for item in planned] == [
        date(2026, 9, 19),
        date(2026, 9, 26),
    ]
    assert [item.ends_on for item in planned] == [
        date(2026, 9, 25),
        date(2026, 10, 2),
    ]
    assert [item.name for item in planned] == [
        "19 Sep – 25 Sep 2026",
        "26 Sep – 2 Oct 2026",
    ]
    assert all(item.goal == "" for item in planned)


def test_raising_ahead_fills_the_buffer(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    assert _planned(session, project) == []

    auto_sprint.set_ahead(project, 2)
    auto_sprint.ensure_open(session, project.id, TODAY)

    assert len(_planned(session, project)) == 2


def test_lowering_ahead_leaves_extra_planned_sprints(
    session: Session,
    project: Project,
) -> None:
    project.sprint_ahead = 2
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first_ids = {item.id for item in _planned(session, project)}

    auto_sprint.set_ahead(project, 1)
    auto_sprint.ensure_open(session, project.id, TODAY)

    remaining = {item.id for item in _planned(session, project)}
    assert remaining == first_ids


def test_rollover_refills_the_ahead_buffer(
    session: Session,
    project: Project,
) -> None:
    project.sprint_ahead = 2
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None
    original = _planned(session, project)
    nxt = original[0]

    auto_sprint.advance_all(session, date(2026, 9, 19))

    assert sprint_service.get_sprint(session, first.id).state is SprintState.COMPLETED
    current = sprint_service.active_sprint(session, project.id)
    assert current is not None
    assert current.id == nxt.id
    planned = _planned(session, project)
    assert len(planned) == 2
    assert planned[0].id == original[1].id
    assert planned[1].starts_on == date(2026, 10, 3)
    assert planned[1].ends_on == date(2026, 10, 9)


def test_undated_planned_sprints_are_dated_from_the_active_window(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    undated = sprint_service.create_sprint(session, project.id, "Soon")
    auto_sprint.set_ahead(project, 2)
    auto_sprint.ensure_open(session, project.id, TODAY)

    filled = sprint_service.get_sprint(session, undated.id)
    assert filled.starts_on == date(2026, 9, 19)
    assert filled.ends_on == date(2026, 9, 25)
    planned = _planned(session, project)
    assert len(planned) == 2
    assert planned[0].id == undated.id
    assert planned[1].starts_on == date(2026, 9, 26)


def test_existing_planned_sprints_count_toward_ahead(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    already = sprint_service.create_sprint(
        session,
        project.id,
        "Already planned",
        starts_on=date(2026, 9, 19),
        ends_on=date(2026, 9, 25),
    )
    auto_sprint.set_ahead(project, 2)
    auto_sprint.ensure_open(session, project.id, TODAY)

    planned = _planned(session, project)
    assert len(planned) == 2
    assert planned[0].id == already.id
    assert planned[0].name == "Already planned"
    assert planned[1].starts_on == date(2026, 9, 26)


def test_a_past_planned_sprint_does_not_count_toward_ahead(
    session: Session,
    project: Project,
) -> None:
    stale = sprint_service.create_sprint(
        session,
        project.id,
        "Stale",
        starts_on=date(2026, 8, 1),
        ends_on=date(2026, 8, 7),
    )
    project.sprint_ahead = 1
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)

    planned = _planned(session, project)
    assert stale.id in {item.id for item in planned}
    usable = [item for item in planned if item.id != stale.id]
    assert len(usable) == 1
    assert usable[0].starts_on == date(2026, 9, 19)


def test_catch_up_with_ahead_still_skips_missed_intervals(
    session: Session,
    project: Project,
) -> None:
    project.sprint_ahead = 2
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None

    auto_sprint.advance_all(session, date(2026, 10, 10))

    listed = sprint_service.list_sprints(session, project.id)
    completed = [item for item in listed if item.state is SprintState.COMPLETED]
    active = [item for item in listed if item.state is SprintState.ACTIVE]
    planned = [item for item in listed if item.state is SprintState.PLANNED]
    assert [item.id for item in completed] == [first.id]
    assert len(active) == 1
    assert active[0].starts_on == date(2026, 10, 10)
    usable = [
        item
        for item in planned
        if item.ends_on is not None and item.ends_on >= date(2026, 10, 10)
    ]
    assert len(usable) == 2
    assert usable[0].starts_on == date(2026, 10, 17)
    assert len(planned) == 4


def test_deleting_a_planned_ahead_sprint_refills_the_buffer(
    session: Session,
    project: Project,
) -> None:
    project.sprint_ahead = 2
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, TODAY)
    first_planned = _planned(session, project)[0]

    auto_sprint.delete_sprint(session, first_planned.id, TODAY)

    planned = _planned(session, project)
    assert len(planned) == 2
    assert first_planned.id not in {item.id for item in planned}


def test_ahead_is_refused_outside_the_allowed_range(
    session: Session,
    project: Project,
) -> None:
    with pytest.raises(InvalidSprintCadenceError) as caught:
        auto_sprint.set_ahead(project, 13)
    assert caught.value.code == "project.invalid_cadence"


def test_ahead_does_nothing_while_auto_sprint_is_off(
    session: Session,
    project: Project,
) -> None:
    auto_sprint.set_ahead(project, 2)
    auto_sprint.ensure_open(session, project.id, TODAY)
    assert sprint_service.list_sprints(session, project.id) == []
