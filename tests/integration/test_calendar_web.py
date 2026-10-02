from datetime import date
from typing import Any

from fastapi.testclient import TestClient

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
    assert "<h2>October 2026</h2>" in page.text
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
    jumped = client.get("/calendar?year=2024&month_num=3")
    assert "<h2>March 2024</h2>" in jumped.text
    assert '<option value="3" selected>March</option>' in jumped.text
    assert '<option value="2024" selected>2024</option>' in jumped.text
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
    label = f"{names[today.month - 1]} {today.year}"
    page = client.get("/calendar?month=nope")
    assert f"<h2>{label}</h2>" in page.text
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
    grace = client.post("/api/v1/users", json={"display_name": "Grace"}).json()
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
    assert "KEEL KEEL-1 Across" in page.text
    assert "SITE SITE-1 Elsewhere" in page.text
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
    assert "<h2>March 2024</h2>" in jumped.text
    assert 'action="/projects/KEEL/calendar"' in jumped.text
    master = client.get("/calendar?month=2026-10")
    assert "In project" not in master.text
    assert "Other project" in master.text
