from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD

Json = dict[str, Any]


def _tester(client: TestClient) -> Json:
    return next(
        user
        for user in client.get("/api/v1/users").json()
        if user["display_name"] == "Tester"
    )


def test_an_empty_month_still_shows_the_grid(client: TestClient) -> None:
    page = client.get("/calendar?month=2026-10")
    assert page.status_code == 200
    assert "<h1>Calendar</h1>" in page.text
    assert "<h2>" not in page.text
    assert "Nothing dated falls in this month." in page.text
    assert ">Mon<" in page.text
    assert ">Sun<" in page.text
    assert 'href="/calendar?month=2026-09"' in page.text
    assert 'href="/calendar?month=2026-11"' in page.text
    assert 'href="/calendar"' in page.text
    assert 'name="month_num"' in page.text
    assert 'name="year"' in page.text
    assert '<option value="10" selected>October</option>' in page.text
    assert '<option value="2026" selected>2026</option>' in page.text
    assert 'action="/calendar"' in page.text
    assert "Show" in page.text
    assert 'class="keel-cal__mode"' in page.text
    assert ">View by:</label>" in page.text
    assert page.text.index(">Day</a>") < page.text.index('id="cal-when"')
    assert page.text.index('id="cal-when"') < page.text.index('aria-label="When"')
    assert '<option value="start" selected>Start to due</option>' in page.text
    assert '<option value="completed">Completed</option>' in page.text
    assert '<option value="created">Created on</option>' in page.text
    chosen = client.get("/calendar?when=completed&month=2026-10")
    assert '<option value="completed" selected>Completed</option>' in chosen.text
    assert "Nothing was completed in this month." in chosen.text
    assert 'href="/calendar?month=2026-09&amp;when=completed"' in chosen.text
    ignored = client.get("/calendar?when=nope&month=2026-10")
    assert '<option value="start" selected>Start to due</option>' in ignored.text
    jumped = client.get("/calendar?year=2024&month_num=3")
    assert "<h2>" not in jumped.text
    assert '<option value="3" selected>March</option>' in jumped.text
    assert '<option value="2024" selected>2024</option>' in jumped.text
    assert 'href="/calendar?view=week&amp;week=2024-03-01"' in jumped.text
    assert 'href="/calendar?view=day&amp;day=2024-03-01"' in jumped.text
    assert "keel-cal__day" in page.text


def test_an_invalid_month_falls_back_to_the_current_month(client: TestClient) -> None:
    today = date.today()
    names = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    page = client.get("/calendar?month=nope")
    assert (
        f'<option value="{today.month}" selected>{names[today.month - 1]}</option>'
        in page.text
    )
    assert f'<option value="{today.year}" selected>{today.year}</option>' in page.text
    assert "<h2>" not in page.text
    assert "Nothing dated falls in this month." in page.text


def test_the_month_lists_assigned_dated_work_and_links_the_issue(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    site = client.post(
        "/api/v1/projects",
        json={"key": "SITE", "name": "Site"},
    ).json()
    tester = _tester(client)
    grace = client.post(
        "/api/v1/users",
        json={"display_name": "Grace", "password": TEST_PASSWORD},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Across",
            "assignee_id": tester["id"],
            "start_at": "2026-09-30T09:00:00",
            "due_at": "2026-10-03T17:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{site['id']}/issues",
        json={
            "type": "story",
            "title": "Elsewhere",
            "assignee_id": tester["id"],
            "due_at": "2026-10-15T09:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Undated",
            "assignee_id": tester["id"],
        },
    )
    finished = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Finished",
            "assignee_id": tester["id"],
            "due_at": "2026-10-15T09:00:00",
        },
    ).json()
    client.patch(
        f"/api/v1/issues/{finished['id']}",
        json={"status": "done"},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Grace's",
            "assignee_id": grace["id"],
            "due_at": "2026-10-15T09:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Unowned",
            "due_at": "2026-10-15T09:00:00",
        },
    )

    page = client.get("/calendar?month=2026-10")
    assert page.status_code == 200
    assert "Nothing dated falls in this month." not in page.text
    assert 'data-type="story"' in page.text
    assert (
        'href="/issues/KEEL-1" style="grid-column: 3 / span 4; grid-row: 1;"'
        in page.text
    )
    assert "KEEL-1 Across" in page.text
    assert "SITE-1 Elsewhere" in page.text
    assert "KEEL KEEL-1 Across" not in page.text
    assert "SITE SITE-1 Elsewhere" not in page.text
    assert "Undated" not in page.text
    assert "Finished" not in page.text
    assert "Grace&#39;s" not in page.text
    assert "Grace's" not in page.text
    assert "Unowned" not in page.text

    november = client.get("/calendar?month=2026-11")
    assert "Across" not in november.text
    assert "Nothing dated falls in this month." in november.text


def test_calendar_follows_the_project_in_the_bar(client: TestClient) -> None:
    client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    home = client.get("/").text
    nav = home.split('<nav class="keel-topbar__nav"', 1)[1].split("</nav>", 1)[0]
    assert (
        nav.index('href="/board"')
        < nav.index('href="/calendar"')
        < nav.index('href="/users"')
    )
    assert ">Calendar<" in nav
    project = client.get("/projects/KEEL").text
    project_nav = project.split('<nav class="keel-topbar__nav"', 1)[1].split(
        "</nav>",
        1,
    )[0]
    assert 'href="/projects/KEEL/calendar"' in project_nav
    assert 'href="/calendar"' not in project_nav
    assert 'href="/projects/KEEL/board"' in project_nav


def test_a_project_calendar_lists_that_projects_dated_work(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    site = client.post(
        "/api/v1/projects",
        json={"key": "SITE", "name": "Site"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "In project",
            "due_at": "2026-10-15T09:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Assigned here",
            "assignee_id": tester["id"],
            "due_at": "2026-10-16T09:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{site['id']}/issues",
        json={
            "type": "story",
            "title": "Other project",
            "assignee_id": tester["id"],
            "due_at": "2026-10-15T09:00:00",
        },
    )

    page = client.get("/projects/KEEL/calendar?month=2026-10")
    assert page.status_code == 200
    assert "In project" in page.text
    assert "Assigned here" in page.text
    assert "Other project" not in page.text
    assert 'href="/projects/KEEL/calendar?month=2026-09"' in page.text
    assert 'href="/projects/KEEL/calendar?month=2026-11"' in page.text
    assert 'action="/projects/KEEL/calendar"' in page.text
    jumped = client.get("/projects/KEEL/calendar?year=2024&month_num=3")
    assert "<h2>" not in jumped.text
    assert '<option value="3" selected>March</option>' in jumped.text
    assert '<option value="2024" selected>2024</option>' in jumped.text
    assert 'action="/projects/KEEL/calendar"' in jumped.text
    master = client.get("/calendar?month=2026-10")
    assert "In project" not in master.text
    assert "Other project" in master.text


def test_the_week_view_steps_seven_days_on_the_same_calendar(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "This week",
            "assignee_id": tester["id"],
            "start_at": "2026-10-14T09:00:00",
            "due_at": "2026-10-16T17:00:00",
        },
    )
    page = client.get("/calendar?view=week&week=2026-10-15")
    assert page.status_code == 200
    assert "<h2>October 12–18, 2026</h2>" in page.text
    assert "KEEL-1 This week" in page.text
    assert "KEEL KEEL-1 This week" not in page.text
    assert "min-height:" in page.text
    assert "Nothing dated falls in this week." not in page.text
    assert 'href="/calendar?view=week&amp;week=2026-10-05"' in page.text
    assert 'href="/calendar?view=week&amp;week=2026-10-19"' in page.text
    assert 'href="/calendar?view=week"' in page.text
    assert 'name="view" value="week"' in page.text
    assert 'aria-current="page">Week</a>' in page.text
    assert "Oct 12" in page.text
    assert "12 AM" in page.text
    assert "11 PM" in page.text
    jumped = client.get("/calendar?view=week&year=2024&month_num=3")
    assert "<h2>February 26 – March 3, 2024</h2>" in jumped.text
    assert 'name="view" value="week"' in jumped.text
    assert "Nothing dated falls in this week." in jumped.text
    project_week = client.get("/projects/KEEL/calendar?view=week&week=2026-10-15")
    assert "This week" in project_week.text
    assert 'action="/projects/KEEL/calendar"' in project_week.text
    assert (
        'href="/projects/KEEL/calendar?view=week&amp;week=2026-10-19"'
        in project_week.text
    )
    assert 'name="view" value="week"' in project_week.text


def test_the_day_view_steps_one_day_on_the_same_calendar(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "This day",
            "assignee_id": tester["id"],
            "start_at": "2026-10-14T09:00:00",
            "due_at": "2026-10-16T17:00:00",
        },
    )
    page = client.get("/calendar?view=day&day=2026-10-15")
    assert page.status_code == 200
    assert "<h2>Thursday</h2>" in page.text
    assert "KEEL-1 This day" in page.text
    assert "KEEL KEEL-1 This day" not in page.text
    assert "min-height:" in page.text
    assert "Nothing dated falls on this day." not in page.text
    assert 'href="/calendar?view=day&amp;day=2026-10-14"' in page.text
    assert 'href="/calendar?view=day&amp;day=2026-10-16"' in page.text
    assert 'href="/calendar?view=day"' in page.text
    assert 'name="view" value="day"' in page.text
    assert 'name="day_num"' in page.text
    assert '<option value="15" selected>15</option>' in page.text
    assert 'aria-current="page">Day</a>' in page.text
    assert "keel-cal--day" in page.text
    assert "12 AM" in page.text
    assert "9 AM" in page.text
    missed = client.get("/calendar?view=day&day=2026-10-13")
    assert "This day" not in missed.text
    assert "Nothing dated falls on this day." in missed.text
    jumped = client.get("/calendar?view=day&year=2024&month_num=2&day_num=31")
    assert "<h2>Thursday</h2>" in jumped.text
    assert '<option value="2" selected>February</option>' in jumped.text
    assert '<option value="29" selected>29</option>' in jumped.text
    assert '<option value="2024" selected>2024</option>' in jumped.text
    assert "Nothing dated falls on this day." in jumped.text
    project_day = client.get("/projects/KEEL/calendar?view=day&day=2026-10-15")
    assert "This day" in project_day.text
    assert 'action="/projects/KEEL/calendar"' in project_day.text
    assert (
        'href="/projects/KEEL/calendar?view=day&amp;day=2026-10-16"' in project_day.text
    )
    assert 'name="view" value="day"' in project_day.text


def test_the_dates_menu_switches_completed_and_created(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    finished = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Filed then finished",
            "assignee_id": tester["id"],
        },
    ).json()
    client.patch(f"/api/v1/issues/{finished['id']}", json={"status": "done"})
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Still open",
            "assignee_id": tester["id"],
        },
    )
    unassigned = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Someone else's"},
    ).json()
    client.patch(f"/api/v1/issues/{unassigned['id']}", json={"status": "done"})

    start = client.get("/calendar")
    assert "Filed then finished" not in start.text
    assert "Still open" not in start.text
    completed = client.get("/calendar?when=completed")
    assert "Filed then finished" in completed.text
    assert "Still open" not in completed.text
    assert "Someone else" not in completed.text
    assert '<option value="completed" selected>Completed</option>' in completed.text
    created = client.get("/calendar?when=created")
    assert "Filed then finished" in created.text
    assert "Still open" in created.text
    assert "Someone else" not in created.text
    project_completed = client.get("/projects/KEEL/calendar?when=completed")
    assert "Someone else" in project_completed.text
    kept = client.get("/calendar?when=completed&filters=1&type=epic")
    assert "Filed then finished" not in kept.text
    assert 'keel-filters__reset" href="/calendar?when=completed"' in kept.text
