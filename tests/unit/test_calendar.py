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


def test_a_week_runs_monday_through_sunday_around_the_chosen_day() -> None:
    today = date(2026, 10, 15)
    assert (
        calendar_service.chosen_week(None, year=None, month_num=None, today=today)
        == today
    )
    assert (
        calendar_service.chosen_week("nope", year=None, month_num=None, today=today)
        == today
    )
    assert calendar_service.parse_day("2026-02-31", today) == today
    shown = calendar_service.blank_week(today, today=today)
    assert shown.view == "week"
    assert len(shown.weeks) == 1
    assert shown.weeks[0].days[0].date == date(2026, 10, 12)
    assert shown.weeks[0].days[6].date == date(2026, 10, 18)
    assert shown.label == "October 12–18, 2026"
    assert shown.weeks[0].days[0].mark == "Oct"
    assert shown.weeks[0].days[1].mark == ""
    assert shown.prev_href == "/calendar?view=week&week=2026-10-05"
    assert shown.next_href == "/calendar?view=week&week=2026-10-19"
    assert shown.today_href == "/calendar?view=week"
    assert shown.day_href == "/calendar?view=day&day=2026-10-15"
    focus = calendar_service.chosen_week(None, year=2024, month_num=3, today=today)
    assert focus == date(2024, 3, 1)
    marched = calendar_service.blank_week(focus, today=today)
    assert marched.weeks[0].days[0].date == date(2024, 2, 26)
    assert marched.label == "February 26 – March 3, 2024"
    assert marched.month_number == 3
    assert marched.weeks[0].days[0].mark == "Feb"
    assert marched.weeks[0].days[4].mark == "Mar"
    nye = calendar_service.blank_week(date(2025, 12, 31), today=today)
    assert nye.label == "December 29, 2025 – January 4, 2026"
    month = calendar_service.blank_month(OCTOBER, today=today)
    assert month.week_href == "/calendar?view=week&week=2026-10-15"
    assert month.day_href == "/calendar?view=day&day=2026-10-15"
    other = calendar_service.blank_month(date(2024, 3, 1), today=today)
    assert other.week_href == "/calendar?view=week&week=2024-03-01"
    assert other.day_href == "/calendar?view=day&day=2024-03-01"


def test_a_week_clips_a_bar_to_those_seven_days(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "This week",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 14, 9, 0),
        due_at=datetime(2026, 10, 20, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Earlier",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 5, 9, 0),
    )

    view = calendar_service.week_calendar(
        session,
        ada.id,
        focus=date(2026, 10, 15),
        today=TODAY,
    )

    wednesday = _block(view, "KEEL-1", date(2026, 10, 14))
    assert (wednesday.start_minute, wednesday.end_minute) == (9 * 60, 24 * 60)
    assert wednesday.continues_before is False
    assert wednesday.continues_after is True
    thursday = _block(view, "KEEL-1", date(2026, 10, 15))
    assert (thursday.start_minute, thursday.end_minute) == (0, 24 * 60)
    assert thursday.continues_before is True
    assert thursday.continues_after is True
    assert view.hours[0] == "12 AM"
    assert view.hours[-1] == "11 PM"
    assert all(
        block.title != "Earlier"
        for week in view.weeks
        for day in week.days
        for block in day.blocks
    )


def _block(
    view: calendar_service.MonthCalendar,
    key: str,
    on: date,
) -> calendar_service.HourBlock:
    found = [
        block
        for week in view.weeks
        for day in week.days
        if day.date == on
        for block in day.blocks
        if block.key == key
    ]
    assert len(found) == 1
    return found[0]


def test_a_day_is_that_date_and_clamps_past_the_end_of_the_month() -> None:
    today = date(2026, 10, 15)
    assert (
        calendar_service.chosen_day(
            None,
            year=None,
            month_num=None,
            day_num=None,
            today=today,
        )
        == today
    )
    assert (
        calendar_service.chosen_day(
            "nope",
            year=None,
            month_num=None,
            day_num=None,
            today=today,
        )
        == today
    )
    shown = calendar_service.blank_day(today, today=today)
    assert shown.view == "day"
    assert shown.label == "Thursday"
    assert len(shown.weeks) == 1
    assert shown.weeks[0].days[0].date == today
    assert shown.weeks[0].days[0].is_today is True
    assert shown.day_number == 15
    assert shown.days_in_month == 31
    assert shown.prev_href == "/calendar?view=day&day=2026-10-14"
    assert shown.next_href == "/calendar?view=day&day=2026-10-16"
    assert shown.today_href == "/calendar?view=day"
    assert shown.week_href == "/calendar?view=week&week=2026-10-15"
    assert shown.month_href == "/calendar?month=2026-10"
    clamped = calendar_service.chosen_day(
        "2026-10-15",
        year=2024,
        month_num=2,
        day_num=31,
        today=today,
    )
    assert clamped == date(2024, 2, 29)
    february = calendar_service.blank_day(clamped, today=today)
    assert february.label == "Thursday"
    assert february.day_number == 29
    assert february.days_in_month == 29
    assert february.month_number == 2


def test_a_day_keeps_a_bar_that_covers_that_date(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Across",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 14, 9, 0),
        due_at=datetime(2026, 10, 16, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Earlier",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 5, 9, 0),
    )

    view = calendar_service.day_calendar(
        session,
        ada.id,
        focus=date(2026, 10, 15),
        today=TODAY,
    )

    block = _block(view, "KEEL-1", date(2026, 10, 15))
    assert (block.start_minute, block.end_minute) == (0, 24 * 60)
    assert block.continues_before is True
    assert block.continues_after is True
    assert all(
        item.title != "Earlier"
        for week in view.weeks
        for day in week.days
        for item in day.blocks
    )


def test_a_same_day_issue_occupies_its_hours_and_shares_a_lane(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Morning",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 15, 9, 0),
        due_at=datetime(2026, 10, 15, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Overlap",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 15, 10, 0),
        due_at=datetime(2026, 10, 15, 11, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Due only",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 10, 30),
    )

    view = calendar_service.day_calendar(
        session,
        ada.id,
        focus=TODAY,
        today=TODAY,
    )

    morning = _block(view, "KEEL-1", TODAY)
    assert (morning.start_minute, morning.end_minute) == (9 * 60, 17 * 60)
    assert morning.continues_before is False
    assert morning.continues_after is False
    overlap = _block(view, "KEEL-2", TODAY)
    assert overlap.lanes == 3
    assert overlap.lane != morning.lane
    due_only = _block(view, "KEEL-3", TODAY)
    assert (due_only.start_minute, due_only.end_minute) == (10 * 60 + 30, 11 * 60 + 30)
