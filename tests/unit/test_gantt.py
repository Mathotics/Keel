from datetime import date, datetime

from sqlalchemy.orm import Session

from keel.domain.enums import DependencyKind, IssueStatus, IssueType
from keel.services import dependencies as dependency_service
from keel.services import gantt as gantt_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.issues import IssueFilters

OCTOBER = date(2026, 10, 1)
TODAY = date(2026, 10, 15)


def _row(chart: gantt_service.GanttChart, key: str) -> gantt_service.GanttRow:
    found = [row for row in chart.rows if row.key == key]
    assert len(found) == 1
    return found[0]


def test_dropdowns_win_and_an_unusable_month_is_today() -> None:
    today = date(2026, 10, 15)
    shown = gantt_service.open_gantt(
        None,  # type: ignore[arg-type]
        None,
        view=None,
        month="1990-06",
        year=2024,
        month_num=3,
        today=today,
    )
    assert shown.view == "month"
    assert shown.month_number == 3
    assert shown.year == 2024
    assert shown.label == "March 2024"
    assert len(shown.columns) == 31
    assert shown.years[0] == 2021
    assert shown.years[-1] == 2031
    early = gantt_service.open_gantt(
        None,  # type: ignore[arg-type]
        None,
        view=None,
        month="1990-06",
        year=None,
        month_num=None,
        today=today,
    )
    assert early.years[0] == 1990
    assert early.month_number == 6
    assert shown.empty is True
    assert shown.today_column is None
    fallback = gantt_service.open_gantt(
        None,  # type: ignore[arg-type]
        None,
        view="nope",
        month="nope",
        year=None,
        month_num=None,
        today=today,
    )
    assert fallback.view == "month"
    assert fallback.month_number == 10
    assert fallback.year == 2026
    assert fallback.today_column == 15
    assert fallback.columns[14].is_today is True
    assert fallback.columns[14].mark == "15"


def test_a_bar_runs_from_start_through_due_and_clips_to_the_month(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Across",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 28, 9, 0),
        due_at=datetime(2026, 10, 2, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Inside",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 6, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "One day",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 15, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Runs out",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 30, 9, 0),
        due_at=datetime(2026, 11, 5, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "September only",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 1, 9, 0),
        due_at=datetime(2026, 9, 30, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Undated",
        assignee_id=ada.id,
    )

    chart = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
    )

    clipped = _row(chart, "KEEL-1")
    assert (clipped.column, clipped.length) == (1, 2)
    assert clipped.continues_before is True
    assert clipped.continues_after is False
    inside = _row(chart, "KEEL-2")
    assert (inside.column, inside.length) == (3, 4)
    assert inside.continues_before is False
    assert inside.point is False
    one_day = _row(chart, "KEEL-3")
    assert (one_day.column, one_day.length) == (15, 1)
    assert one_day.point is True
    runs_out = _row(chart, "KEEL-4")
    assert (runs_out.column, runs_out.length) == (30, 2)
    assert runs_out.continues_after is True
    assert [row.key for row in chart.rows] == [
        "KEEL-1",
        "KEEL-2",
        "KEEL-3",
        "KEEL-4",
    ]
    assert chart.prev_href == "/gantt?month=2026-09"
    assert chart.next_href == "/gantt?month=2026-11"
    assert chart.today_href == "/gantt"
    assert chart.quarter_href == "/gantt?view=quarter&month=2026-10"
    assert chart.year_href == "/gantt?view=year&month=2026-01"
    assert "September only" not in [row.title for row in chart.rows]
    assert "Undated" not in [row.title for row in chart.rows]


def test_the_master_chart_keeps_other_people_off_and_a_project_chart_does_not(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    other = project_service.create_project(session, "SITE", "Site")
    ada = user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Mine",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 4, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Hers",
        assignee_id=grace.id,
        due_at=datetime(2026, 10, 4, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Nobody",
        due_at=datetime(2026, 10, 4, 9, 0),
    )
    issue_service.create_issue(
        session,
        other.id,
        IssueType.STORY,
        "Elsewhere",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 4, 9, 0),
    )
    finished = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Finished",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 8, 9, 0),
    )
    issue_service.update_issue(session, finished.id, status=IssueStatus.DONE)

    master = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
    )
    assert [row.title for row in master.rows] == ["Mine", "Elsewhere", "Finished"]
    assert _row(master, "KEEL-4").status is IssueStatus.DONE

    project_chart = gantt_service.open_gantt(
        session,
        None,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
        project_id=project.id,
        base="/projects/KEEL/gantt",
    )
    assert [row.title for row in project_chart.rows] == [
        "Mine",
        "Hers",
        "Nobody",
        "Finished",
    ]
    assert project_chart.base == "/projects/KEEL/gantt"
    assert "Elsewhere" not in [row.title for row in project_chart.rows]

    todo = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
        filters=IssueFilters(statuses=(IssueStatus.TODO,)),
    )
    assert [row.title for row in todo.rows] == ["Mine", "Elsewhere"]


def test_a_child_sits_under_its_parent_when_the_parent_is_on_the_page(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    epic = issue_service.create_issue(
        session,
        project.id,
        IssueType.EPIC,
        "Epic",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 10, 9, 0),
        due_at=datetime(2026, 10, 20, 17, 0),
    )
    story = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Story",
        assignee_id=ada.id,
        parent_id=epic.id,
        start_at=datetime(2026, 10, 2, 9, 0),
        due_at=datetime(2026, 10, 4, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.SUBTASK,
        "Subtask",
        assignee_id=ada.id,
        parent_id=story.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 3, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Loose",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 1, 9, 0),
        due_at=datetime(2026, 10, 1, 17, 0),
    )
    hidden = issue_service.create_issue(
        session,
        project.id,
        IssueType.EPIC,
        "Undated epic",
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Orphan",
        assignee_id=ada.id,
        parent_id=hidden.id,
        due_at=datetime(2026, 10, 6, 9, 0),
    )

    chart = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
    )
    assert [row.title for row in chart.rows] == [
        "Loose",
        "Orphan",
        "Epic",
        "Story",
        "Subtask",
    ]
    assert _row(chart, "KEEL-1").depth == 0
    assert _row(chart, "KEEL-2").depth == 1
    assert _row(chart, "KEEL-3").depth == 2
    assert _row(chart, "KEEL-6").depth == 0


def test_a_quarter_uses_one_column_per_week(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Two weeks",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 6, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "One day",
        assignee_id=ada.id,
        due_at=datetime(2026, 11, 15, 9, 0),
    )

    chart = gantt_service.open_gantt(
        session,
        ada.id,
        view="quarter",
        month="2026-11",
        year=None,
        month_num=None,
        today=TODAY,
        base="/gantt",
    )
    assert chart.view == "quarter"
    assert chart.label == "October–December 2026"
    assert chart.month_number == 10
    assert len(chart.columns) == 14
    assert chart.columns[0].mark == "Sep 28"
    assert chart.columns[0].hint == "Week of September 28, 2026"
    assert chart.today_column == 3
    two_weeks = _row(chart, "KEEL-1")
    assert (two_weeks.column, two_weeks.length) == (1, 2)
    assert two_weeks.point is False
    one_day = _row(chart, "KEEL-2")
    assert (one_day.column, one_day.length) == (7, 1)
    assert one_day.point is False
    assert chart.prev_href == "/gantt?view=quarter&month=2026-07"
    assert chart.next_href == "/gantt?view=quarter&month=2027-01"
    assert chart.today_href == "/gantt?view=quarter"
    assert chart.month_href == "/gantt?month=2026-10"
    early = gantt_service.open_gantt(
        session,
        ada.id,
        view="quarter",
        month="2026-01",
        year=None,
        month_num=None,
        today=TODAY,
    )
    assert early.month_href == "/gantt?month=2026-01"
    assert early.label == "January–March 2026"
    assert early.year_href == "/gantt?view=year&month=2026-01"
    assert early.empty is True
    assert early.links == ()


def test_a_year_uses_one_column_per_month(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "October",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 6, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Into next year",
        assignee_id=ada.id,
        start_at=datetime(2026, 11, 20, 9, 0),
        due_at=datetime(2027, 2, 4, 17, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Last December",
        assignee_id=ada.id,
        start_at=datetime(2025, 12, 20, 9, 0),
        due_at=datetime(2026, 1, 3, 17, 0),
    )

    chart = gantt_service.open_gantt(
        session,
        ada.id,
        view="year",
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
    )
    assert chart.view == "year"
    assert chart.label == "2026"
    assert chart.month_number == 1
    assert len(chart.columns) == 12
    assert chart.columns[0].mark == "Jan"
    assert chart.columns[0].hint == "January 2026"
    assert chart.today_column == 10
    assert chart.columns[9].is_today is True
    october = _row(chart, "KEEL-1")
    assert (october.column, october.length) == (10, 1)
    assert october.point is False
    spanning = _row(chart, "KEEL-2")
    assert (spanning.column, spanning.length) == (11, 2)
    assert spanning.continues_after is True
    carried = _row(chart, "KEEL-3")
    assert (carried.column, carried.length) == (1, 1)
    assert carried.continues_before is True
    assert chart.prev_href == "/gantt?view=year&month=2025-01"
    assert chart.next_href == "/gantt?view=year&month=2027-01"
    assert chart.today_href == "/gantt?view=year"
    assert chart.month_href == "/gantt?month=2026-10"
    assert chart.quarter_href == "/gantt?view=quarter&month=2026-10"
    other = gantt_service.open_gantt(
        session,
        ada.id,
        view="year",
        month="2024-06",
        year=None,
        month_num=None,
        today=TODAY,
    )
    assert other.label == "2024"
    assert other.month_href == "/gantt?month=2024-01"
    assert other.quarter_href == "/gantt?view=quarter&month=2024-01"
    assert other.empty is True
    assert other.empty_note == "Nothing dated falls in this year."


def test_a_link_is_drawn_only_when_both_issues_are_rows(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    other = project_service.create_project(session, "SITE", "Site")
    ada = user_service.create_user(session, "Ada")
    first = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "First",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 6, 17, 0),
    )
    second = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Second",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 10, 9, 0),
        due_at=datetime(2026, 10, 12, 17, 0),
    )
    hidden = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "September",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 1, 9, 0),
        due_at=datetime(2026, 9, 4, 17, 0),
    )
    elsewhere = issue_service.create_issue(
        session,
        other.id,
        IssueType.STORY,
        "Elsewhere",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 8, 9, 0),
        due_at=datetime(2026, 10, 9, 17, 0),
    )
    finished = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Finished",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 20, 9, 0),
        due_at=datetime(2026, 10, 21, 17, 0),
    )
    issue_service.update_issue(session, finished.id, status=IssueStatus.DONE)
    dependency_service.create_dependency(
        session,
        first.id,
        second.id,
        DependencyKind.BLOCKS,
    )
    dependency_service.create_dependency(
        session,
        second.id,
        finished.id,
        DependencyKind.RELATES_TO,
    )
    dependency_service.create_dependency(
        session,
        first.id,
        hidden.id,
        DependencyKind.BLOCKS,
    )
    dependency_service.create_dependency(
        session,
        first.id,
        elsewhere.id,
        DependencyKind.RELATES_TO,
    )

    chart = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
    )
    assert [link.text for link in chart.links] == [
        "KEEL-1 blocks KEEL-2",
        "KEEL-1 relates to SITE-1",
        "KEEL-2 relates to KEEL-4",
    ]
    blocks = chart.links[0]
    assert blocks.kind == "blocks"
    assert blocks.path == "M 6 0.5 L 6.45 0.5 L 6.45 2.5 L 9 2.5"
    assert blocks.tip == "right"
    assert blocks.tip_x == "29.03"
    assert blocks.tip_y == "62.5"
    relates = chart.links[2]
    assert relates.kind == "relates_to"
    assert relates.tip == ""
    assert relates.path == "M 10.5 2.5 L 10.5 2.92 L 20 2.92 L 20 3.5"
    assert "September" not in relates.text

    project_chart = gantt_service.open_gantt(
        session,
        None,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
        project_id=project.id,
    )
    assert "SITE-1" not in [link.text for link in project_chart.links]
    assert "KEEL-1 blocks KEEL-2" in [link.text for link in project_chart.links]

    todo = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
        filters=IssueFilters(statuses=(IssueStatus.TODO,)),
    )
    assert [link.text for link in todo.links] == [
        "KEEL-1 blocks KEEL-2",
        "KEEL-1 relates to SITE-1",
    ]


def test_a_blocks_arrow_routes_back_when_the_blocked_issue_starts_earlier(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    ada = user_service.create_user(session, "Ada")
    early = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Early",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 3, 9, 0),
        due_at=datetime(2026, 10, 4, 17, 0),
    )
    late = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Late",
        assignee_id=ada.id,
        start_at=datetime(2026, 10, 10, 9, 0),
        due_at=datetime(2026, 10, 12, 17, 0),
    )
    dependency_service.create_dependency(
        session,
        late.id,
        early.id,
        DependencyKind.BLOCKS,
    )
    chart = gantt_service.open_gantt(
        session,
        ada.id,
        view=None,
        month="2026-10",
        year=None,
        month_num=None,
        today=TODAY,
    )
    link = chart.links[0]
    assert link.text == "KEEL-2 blocks KEEL-1"
    assert link.path == (
        "M 12 1.5 L 12.45 1.5 L 12.45 0.68 L 1.55 0.68 L 1.55 0.5 L 2 0.5"
    )
    assert link.tip == "right"
