from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project, Series
from keel.domain.enums import (
    EditScope,
    IssueStatus,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
)
from keel.domain.errors import InvalidSeriesError
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import series_tree
from keel.services.series_tree import ItemDraft


def _project(session: Session) -> Project:
    return project_service.create_project(session, "HOME", "Home")


def _draft(
    title: str,
    kind: IssueType,
    *,
    key: str,
    parent_key: str | None = None,
    due_offset_days: int | None = None,
    due_minute_of_day: int | None = None,
) -> ItemDraft:
    return ItemDraft(
        title=title,
        type=kind,
        key=key,
        parent_key=parent_key,
        due_offset_days=due_offset_days,
        due_minute_of_day=due_minute_of_day,
    )


def _yearly(session: Session, project_id: int, **kwargs: object) -> Series:
    payload: dict[str, object] = {
        "title": "File taxes",
        "type": IssueType.EPIC,
        "spawn_mode": SeriesSpawnMode.CALENDAR,
        "sprint_basis": SeriesSprintBasis.DUE_ON,
        "freq": RecurrenceFreq.YEARLY,
        "starts_on": date(2026, 4, 15),
        "month": 4,
        "month_day": 15,
        "look_ahead_n": 1,
        "due_offset_days": 0,
        "due_minute_of_day": 17 * 60,
        "today": date(2026, 4, 1),
        "items": [
            _draft("File federal return", IssueType.STORY, key="federal"),
            _draft(
                "Fill out the form",
                IssueType.SUBTASK,
                key="form",
                parent_key="federal",
            ),
            _draft("File state returns", IssueType.STORY, key="state"),
        ],
    }
    payload.update(kwargs)
    return series_service.create_series(session, project_id, **payload)  # type: ignore[arg-type]


FEDERAL = "File federal return"


def _named(session: Session, series_id: int, title: str) -> list[Issue]:
    return [issue for issue in _copies(session, series_id) if issue.title == title]


def _copies(session: Session, series_id: int) -> list[Issue]:
    return list(
        session.scalars(
            select(Issue)
            .where(Issue.series_id == series_id)
            .order_by(Issue.occurrence_on, Issue.id),
        ).all(),
    )


def test_a_schedule_spawns_the_whole_tree(session: Session) -> None:
    project = _project(session)
    series = _yearly(session, project.id)
    copies = _copies(session, series.id)
    roots = [issue for issue in copies if issue.series_item_id is None]
    assert len(roots) == 1
    assert roots[0].title == "File taxes"
    federal = next(issue for issue in copies if issue.title == "File federal return")
    form = next(issue for issue in copies if issue.title == "Fill out the form")
    state = next(issue for issue in copies if issue.title == "File state returns")
    assert federal.parent_id == roots[0].id
    assert state.parent_id == roots[0].id
    assert form.parent_id == federal.id
    assert federal.occurrence_on == roots[0].occurrence_on
    assert form.series_item_id is not None
    assert state.sprint_id is None


def test_after_closed_waits_only_for_the_root(session: Session) -> None:
    project = _project(session)
    series = _yearly(
        session,
        project.id,
        spawn_mode=SeriesSpawnMode.AFTER_CLOSED,
        look_ahead_n=1,
    )
    first = _copies(session, series.id)
    assert len(first) == 4
    root = next(issue for issue in first if issue.series_item_id is None)
    issue_service.update_issue(session, root.id, status=IssueStatus.DONE)
    second = _copies(session, series.id)
    roots = [issue for issue in second if issue.series_item_id is None]
    assert len(roots) == 2
    still_open = [
        issue
        for issue in first
        if issue.status is not IssueStatus.DONE and issue.title == FEDERAL
    ]
    assert still_open


def test_a_blank_child_date_stays_unscheduled(session: Session) -> None:
    project = _project(session)
    series = _yearly(session, project.id)
    federal = _named(session, series.id, FEDERAL)[0]
    assert federal.due_at is None
    assert federal.sprint_id is None


def test_saving_the_schedule_does_not_rewrite_an_open_tree(session: Session) -> None:
    project = _project(session)
    series = _yearly(session, project.id)
    federal = _named(session, series.id, FEDERAL)[0]
    items = series_tree.active_items(session, series.id)
    series_service.update_series(
        session,
        series.id,
        items=[
            ItemDraft(
                title="File federal return renamed",
                type=item.type,
                item_id=item.id,
                key=f"id:{item.id}",
                parent_key=(
                    None if item.parent_item_id is None else f"id:{item.parent_item_id}"
                ),
            )
            for item in items
        ]
        + [
            _draft(
                "Upload receipts",
                IssueType.SUBTASK,
                key="receipts",
                parent_key=f"id:{items[0].id}",
            ),
        ],
        today=date(2026, 4, 1),
    )
    session.refresh(federal)
    assert federal.title == FEDERAL
    titles = {issue.title for issue in _copies(session, series.id)}
    assert "Upload receipts" not in titles
    saved = series_tree.active_items(session, series.id)
    assert any(item.title == "Upload receipts" for item in saved)


def test_occurrence_scopes_add_and_remove_one_item(session: Session) -> None:
    project = _project(session)
    series = _yearly(session, project.id, look_ahead_n=2)
    roots = [
        issue for issue in _copies(session, series.id) if issue.series_item_id is None
    ]
    assert len(roots) >= 1
    current = roots[0]
    series_service.apply_occurrence_edit(
        session,
        current.id,
        EditScope.THIS,
        item_action="add",
        item=_draft("Just this year", IssueType.STORY, key="once"),
    )
    once = session.scalar(select(Issue).where(Issue.title == "Just this year"))
    assert once is not None
    assert once.series_id is None
    assert once.parent_id == current.id
    series_service.apply_occurrence_edit(
        session,
        current.id,
        EditScope.FUTURE,
        item_action="add",
        item=_draft("Every year", IssueType.STORY, key="every"),
    )
    every = [
        issue for issue in _copies(session, series.id) if issue.title == "Every year"
    ]
    assert every
    assert all(issue.series_item_id is not None for issue in every)
    parent_ids = {root.id for root in roots}
    assert all(issue.parent_id in parent_ids for issue in every)
    target = every[0]
    series_service.apply_occurrence_edit(
        session,
        target.id,
        EditScope.SERIES,
        title="Every year renamed",
    )
    renamed = [
        issue
        for issue in _copies(session, series.id)
        if issue.series_item_id == target.series_item_id
        and issue.status is not IssueStatus.DONE
    ]
    assert renamed
    assert {issue.title for issue in renamed} == {"Every year renamed"}
    series_service.apply_occurrence_edit(
        session,
        target.id,
        EditScope.THIS,
        item_action="remove",
    )
    assert session.get(Issue, target.id) is None
    assert any(
        item.title == "Every year renamed"
        for item in series_tree.active_items(session, series.id)
    )


def test_seed_keeps_the_tree_as_the_first_occurrence(session: Session) -> None:
    project = _project(session)
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="File taxes",
    )
    story = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title=FEDERAL,
        parent_id=epic.id,
    )
    form = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.SUBTASK,
        title="Fill out the form",
        parent_id=story.id,
    )
    series = series_service.create_series(
        session,
        project.id,
        title=epic.title,
        type=IssueType.EPIC,
        spawn_mode=SeriesSpawnMode.CALENDAR,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.YEARLY,
        starts_on=date(2026, 4, 15),
        month=4,
        month_day=15,
        look_ahead_n=1,
        seed_issue_id=epic.id,
        today=date(2026, 4, 1),
    )
    session.refresh(story)
    session.refresh(form)
    assert story.series_id == series.id
    assert form.series_id == series.id
    assert story.occurrence_on == epic.occurrence_on
    assert form.parent_id == story.id
    same_day = [
        issue
        for issue in _copies(session, series.id)
        if issue.occurrence_on == epic.occurrence_on and issue.title == FEDERAL
    ]
    assert len(same_day) == 1


def test_a_closed_copy_keeps_its_own_title(session: Session) -> None:
    project = _project(session)
    series = _yearly(session, project.id, look_ahead_n=2)
    copies = _named(session, series.id, FEDERAL)
    assert len(copies) >= 2
    closed = copies[0]
    issue_service.update_issue(session, closed.id, status=IssueStatus.DONE)
    series_service.apply_occurrence_edit(
        session,
        copies[1].id,
        EditScope.SERIES,
        title="Federal renamed",
    )
    session.refresh(closed)
    assert closed.title == FEDERAL
    session.refresh(copies[1])
    assert copies[1].title == "Federal renamed"


def test_an_illegal_parent_is_refused(session: Session) -> None:
    project = _project(session)
    with pytest.raises(InvalidSeriesError):
        _yearly(
            session,
            project.id,
            items=[_draft("Another epic", IssueType.EPIC, key="nope")],
        )


def test_deleting_the_root_removes_that_occurrence(session: Session) -> None:
    project = _project(session)
    series = _yearly(session, project.id)
    root = next(
        issue for issue in _copies(session, series.id) if issue.series_item_id is None
    )
    occurrence = root.occurrence_on
    issue_service.delete_issue(session, root.id)
    assert not [
        issue
        for issue in _copies(session, series.id)
        if issue.occurrence_on == occurrence
    ]
    series_service.advance_series(session, series.id, date(2026, 4, 1))
    assert not [
        issue
        for issue in _copies(session, series.id)
        if issue.occurrence_on == occurrence
    ]
