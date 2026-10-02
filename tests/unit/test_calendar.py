from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from keel.domain.enums import IssueStatus, IssueType
from keel.services import calendar as calendar_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service

OCTOBER = date(2026, 10, 1)
TODAY = date(2026, 10, 15)


def _span(
    view: calendar_service.MonthCalendar, key: str
) -> calendar_service.CalendarSpan:
    found = [span for week in view.weeks for span in week.spans if span.key == key]
    assert len(found) == 1
    return found[0]


def test_dropdowns_jump_to_the_chosen_month_and_year() -> None:
    today = date(2026, 10, 15)
    assert calendar_service.chosen_month(
        None,
        year=2024,
        month_num=3,
        today=today,
    ) == date(2024, 3, 1)
    assert calendar_service.chosen_month(
        "2026-10",
        year=None,
        month_num=None,
        today=today,
    ) == date(2026, 10, 1)
    assert calendar_service.chosen_month(
        "2026-10",
        year=1999,
        month_num=13,
        today=date(2026, 11, 2),
    ) == date(2026, 11, 1)
    shown = calendar_service.blank_month(date(1990, 6, 1), today=today)
    assert shown.years[0] == 1990
    assert shown.years[-1] == 2031
    assert shown.month_number == 6
    assert shown.year == 1990


def test_a_missing_or_invalid_month_is_the_current_month() -> None:
    today = date(2026, 10, 15)
    assert calendar_service.parse_month(None, today) == OCTOBER
    assert calendar_service.parse_month("   ", today) == OCTOBER
    assert calendar_service.parse_month("nope", today) == OCTOBER
    assert calendar_service.parse_month("2026-13", today) == OCTOBER
    assert calendar_service.parse_month("2026-10-01", today) == OCTOBER
    assert calendar_service.parse_month("2026-04", today) == date(2026, 4, 1)


def test_a_span_runs_from_start_through_due_and_clips_to_the_week(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Across the first",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 30, 9, 0),
        due_at=datetime(2026, 10, 3, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "From last month",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 1, 9, 0),
        due_at=datetime(2026, 10, 2, 17, 0),
    )

    view = calendar_service.month_calendar(
        session,
        ada.id,
        month=OCTOBER,
        today=TODAY,
    )

    across = _span(view, "KEEL-1")
    assert (across.column, across.length) == (3, 4)
    clipped = _span(view, "KEEL-2")
    assert (clipped.column, clipped.length) == (1, 5)
    assert view.label == "October 2026"
    assert view.prev_month == "2026-09"
    assert view.next_month == "2026-11"
    assert view.empty is False


def test_a_bar_that_crosses_a_sunday_continues_on_the_next_week(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Over the weekend",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 6, 17, 0),
    )

    view = calendar_service.month_calendar(
        session,
        ada.id,
        month=OCTOBER,
        today=TODAY,
    )

    pieces = [
        (span.column, span.length, span.continues_before, span.continues_after)
        for week in view.weeks
        for span in week.spans
        if span.key == "KEEL-1"
    ]
    assert pieces == [(6, 2, False, True), (1, 2, True, False)]


def test_one_date_is_a_single_day_and_none_is_omitted(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Due only",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 1, 0, tzinfo=UTC),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Start only",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 16, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Undated",
        assignee_id=ada.id,
    )

    view = calendar_service.month_calendar(
        session,
        ada.id,
        month=OCTOBER,
        today=TODAY,
    )

    due = _span(view, "KEEL-1")
    start = _span(view, "KEEL-2")
    assert (due.column, due.length, due.title) == (4, 1, "Due only")
    assert (start.column, start.length) == (5, 1)
    assert all(span.title != "Undated" for week in view.weeks for span in week.spans)


def test_closed_and_other_people_stay_off_the_month(session: Session) -> None:
    keel = project_service.create_project(session, "KEEL", "Keel")
    site = project_service.create_project(session, "SITE", "Site")
    ada = user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Mine",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )
    issue_service.create_issue(
        session,
        site.id,
        IssueType.STORY,
        "Also mine",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 15, 9, 0),
        due_at=datetime(2026, 10, 15, 17, 0),
    )
    done = issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Finished",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )
    issue_service.update_issue(session, done.id, status=IssueStatus.DONE)
    cancelled = issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Dropped",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )
    issue_service.update_issue(session, cancelled.id, status=IssueStatus.CANCELLED)
    issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Grace's",
        assignee_id=grace.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )
    issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Unassigned",
        due_at=datetime(2026, 10, 15, 9, 0),
    )

    view = calendar_service.month_calendar(
        session,
        ada.id,
        month=OCTOBER,
        today=TODAY,
    )

    titles = [span.title for week in view.weeks for span in week.spans]
    assert titles == ["Mine", "Also mine"]
    assert {span.project_key for week in view.weeks for span in week.spans} == {
        "KEEL",
        "SITE",
    }
    same_day = [span for week in view.weeks for span in week.spans if span.column == 4]
    assert [span.lane for span in same_day] == [1, 2]


def test_a_project_month_includes_every_dated_issue_in_that_project(
    session: Session,
) -> None:
    keel = project_service.create_project(session, "KEEL", "Keel")
    site = project_service.create_project(session, "SITE", "Site")
    ada = user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Mine",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )
    issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Unassigned",
        due_at=datetime(2026, 10, 16, 9, 0),
    )
    issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Grace's",
        assignee_id=grace.id,
        due_at=datetime(2026, 10, 17, 9, 0),
    )
    issue_service.create_issue(
        session,
        site.id,
        IssueType.STORY,
        "Other project",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )

    view = calendar_service.month_calendar(
        session,
        month=OCTOBER,
        today=TODAY,
        project_id=keel.id,
        base="/projects/KEEL/calendar",
    )

    titles = [span.title for week in view.weeks for span in week.spans]
    assert titles == ["Mine", "Unassigned", "Grace's"]
    assert view.base == "/projects/KEEL/calendar"


def test_a_bar_carries_the_issue_type(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.EPIC,
        "Epic",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 12, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Story",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 13, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.SUBTASK,
        "Subtask",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 14, 9, 0),
    )

    view = calendar_service.month_calendar(session, ada.id, month=OCTOBER, today=TODAY)

    assert _span(view, "KEEL-1").type == "epic"
    assert _span(view, "KEEL-2").type == "story"
    assert _span(view, "KEEL-3").type == "subtask"


def test_a_month_with_nothing_dated_still_has_its_grid(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Later",
        assignee_id=ada.id,
        due_at=datetime(2026, 11, 2, 9, 0),
    )

    view = calendar_service.month_calendar(
        session,
        ada.id,
        month=OCTOBER,
        today=TODAY,
    )

    assert view.empty is True
    assert view.weeks
    assert all(len(week.days) == 7 for week in view.weeks)
    assert view.weeks[0].days[0].date == date(2026, 9, 28)
    assert view.weeks[0].days[0].date.weekday() == 0
    blank = calendar_service.blank_month(OCTOBER, today=TODAY)
    assert blank.empty is True
    assert blank.label == "October 2026"
    assert any(day.is_today for week in blank.weeks for day in week.days)
