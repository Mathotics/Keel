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


def test_an_empty_month_still_shows_the_days(client: TestClient) -> None:
    page = client.get("/gantt?month=2026-10")
    assert page.status_code == 200
    assert "<h1>Gantt</h1>" in page.text
    assert "<h2>" not in page.text
    assert "Nothing dated falls in this month." in page.text
    assert page.text.count('class="keel-gantt__col') == 31
    assert 'href="/gantt?month=2026-09"' in page.text
    assert 'href="/gantt?month=2026-11"' in page.text
    assert 'href="/gantt?view=quarter&amp;month=2026-10"' in page.text
    assert 'href="/gantt"' in page.text
    assert 'name="month_num"' in page.text
    assert 'name="year"' in page.text
    assert '<option value="10" selected>October</option>' in page.text
    assert '<option value="2026" selected>2026</option>' in page.text
    assert 'action="/gantt"' in page.text
    assert "Show" in page.text
    assert 'aria-current="page"' in page.text
    jumped = client.get("/gantt?year=2024&month_num=3")
    assert '<option value="3" selected>March</option>' in jumped.text
    assert '<option value="2024" selected>2024</option>' in jumped.text
    assert 'href="/gantt?view=quarter&amp;month=2024-01"' in jumped.text


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
    page = client.get("/gantt?month=nope")
    assert (
        f'<option value="{today.month}" selected>{names[today.month - 1]}</option>'
        in page.text
    )
    assert f'<option value="{today.year}" selected>{today.year}</option>' in page.text
    quarter = client.get("/gantt?view=quarter&month=nope")
    first = ((today.month - 1) // 3) * 3
    assert f"<h2>{names[first]}–{names[first + 2]} {today.year}</h2>" in quarter.text


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
            "start_at": "2026-10-03T09:00:00",
            "due_at": "2026-10-06T17:00:00",
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
    client.patch(f"/api/v1/issues/{finished['id']}", json={"status": "done"})
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Grace work",
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

    page = client.get("/gantt?month=2026-10")
    assert page.status_code == 200
    assert "Nothing dated falls in this month." not in page.text
    assert 'data-type="story"' in page.text
    assert 'href="/issues/KEEL-1"' in page.text
    assert 'style="grid-column: 3 / span 4;"' in page.text
    assert "KEEL-1" in page.text
    assert "Across" in page.text
    assert 'class="keel-gantt__status" data-status="todo">To Do</span>' in page.text
    assert "SITE-1" in page.text
    assert "Elsewhere" in page.text
    assert "KEEL KEEL-1" not in page.text
    assert "Undated" not in page.text
    assert "Finished" in page.text
    assert 'data-status="done">Done</span>' in page.text
    assert "Grace work" not in page.text
    assert "Unowned" not in page.text
    todo_only = client.get("/gantt?month=2026-10&status=todo")
    assert "Across" in todo_only.text
    assert "Finished" not in todo_only.text
    assert 'href="/gantt?month=2026-09&amp;status=todo"' in todo_only.text
    assert 'href="/gantt?month=2026-10"' in todo_only.text
    november = client.get("/gantt?month=2026-11")
    assert "Across" not in november.text
    assert "Nothing dated falls in this month." in november.text

    project_page = client.get("/projects/KEEL/gantt?month=2026-10")
    assert "Grace work" in project_page.text
    assert "Unowned" in project_page.text
    assert "Elsewhere" not in project_page.text
    assert 'action="/projects/KEEL/gantt"' in project_page.text


def test_a_dependency_between_two_rows_is_drawn(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    first = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "First",
            "assignee_id": tester["id"],
            "start_at": "2026-10-03T09:00:00",
            "due_at": "2026-10-06T17:00:00",
        },
    ).json()
    second = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Second",
            "assignee_id": tester["id"],
            "start_at": "2026-10-10T09:00:00",
            "due_at": "2026-10-12T17:00:00",
        },
    ).json()
    client.post(
        "/api/v1/dependencies",
        json={
            "source_id": first["id"],
            "target_id": second["id"],
            "kind": "blocks",
        },
    )
    page = client.get("/gantt?month=2026-10")
    assert page.status_code == 200
    assert 'data-kind="blocks"' in page.text
    assert "KEEL-1 blocks KEEL-2" in page.text
    assert "A solid arrow means blocks." in page.text
    assert 'class="keel-gantt__tip keel-gantt__tip--right"' in page.text


def test_gantt_follows_the_project_in_the_bar(client: TestClient) -> None:
    client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    home = client.get("/").text
    nav = home.split('<nav class="keel-topbar__nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.index('href="/calendar"') < nav.index('href="/gantt"')
    assert ">Gantt<" in nav
    project = client.get("/projects/KEEL").text
    project_nav = project.split('<nav class="keel-topbar__nav"', 1)[1].split(
        "</nav>",
        1,
    )[0]
    assert 'href="/projects/KEEL/gantt"' in project_nav
    assert 'href="/gantt"' not in project_nav
