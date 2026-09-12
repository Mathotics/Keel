from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

Json = dict[str, Any]


@pytest.fixture
def project(client: TestClient) -> Json:
    created: Json = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    return created


def test_an_end_before_the_start_returns_to_the_form_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    page = client.get("/projects/KEEL/sprints")
    assert 'data-keel-range="start"' in page.text
    assert 'data-keel-range="end"' in page.text

    created = client.post(
        f"/web/projects/{project['id']}/sprints",
        data={
            "name": "Sprint 1",
            "starts_on": "2026-09-10",
            "ends_on": "2026-09-01",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]
    assert location.startswith("/projects/KEEL/sprints?error=")
    assert "cannot end before it starts" in client.get(location).text


def test_saving_an_end_before_the_start_returns_to_the_sprint(
    client: TestClient,
    project: Json,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Sprint 1", "starts_on": "2026-09-10"},
    ).json()

    page = client.get(f"/projects/KEEL/sprints/{sprint['id']}")
    assert 'min="2026-09-10"' in page.text

    saved = client.post(
        f"/web/sprints/{sprint['id']}/update",
        data={
            "name": "Sprint 1",
            "starts_on": "2026-09-10",
            "ends_on": "2026-09-01",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    location = saved.headers["location"]
    assert location.startswith(f"/projects/KEEL/sprints/{sprint['id']}?error=")
    assert "cannot end before it starts" in client.get(location).text
    assert client.get(f"/api/v1/sprints/{sprint['id']}").json()["ends_on"] is None


def test_the_sprints_page_creates_and_lists_a_sprint(
    client: TestClient,
    project: Json,
) -> None:
    created = client.post(
        f"/web/projects/{project['id']}/sprints",
        data={"name": "Sprint 1", "goal": "Ship it", "starts_on": "2026-09-01"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]
    assert location.startswith("/projects/KEEL/sprints/")

    listing = client.get("/projects/KEEL/sprints")
    assert listing.status_code == 200
    assert "Sprint 1" in listing.text
    assert "Ship it" in listing.text
    assert "Plan a sprint" in listing.text


def test_the_backlog_schedules_an_issue_into_a_planned_sprint(
    client: TestClient,
    project: Json,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Sprint 1"},
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Waiting"},
    ).json()

    page = client.get("/projects/KEEL/backlog")
    assert page.status_code == 200
    assert "Waiting" in page.text
    assert "data-keel-autosubmit" in page.text
    assert ">Schedule<" in page.text

    scheduled = client.post(
        f"/web/issues/{issue['id']}/sprint",
        data={"sprint_id": str(sprint["id"]), "next": "/projects/KEEL/backlog"},
        follow_redirects=False,
    )
    assert scheduled.status_code == 303
    assert scheduled.headers["location"] == "/projects/KEEL/backlog"
    assert "Waiting" not in client.get("/projects/KEEL/backlog").text


def test_starting_a_second_sprint_returns_to_the_page_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    first = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "One"},
    ).json()
    second = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Two"},
    ).json()
    client.post(f"/api/v1/sprints/{first['id']}/start")

    response = client.post(
        f"/web/sprints/{second['id']}/start",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    page = client.get(response.headers["location"])
    assert "already has an active sprint" in page.text


def test_a_sprint_from_another_project_is_not_found(
    client: TestClient,
    project: Json,
) -> None:
    other = client.post("/api/v1/projects", json={"key": "SITE", "name": "Site"}).json()
    foreign = client.post(
        f"/api/v1/projects/{other['id']}/sprints",
        json={"name": "Site sprint"},
    ).json()

    assert (
        client.get(f"/projects/{project['key']}/sprints/{foreign['id']}").status_code
        == 404
    )


def test_completing_a_planned_sprint_returns_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Waiting"},
    ).json()

    response = client.post(
        f"/web/sprints/{sprint['id']}/complete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    page = client.get(response.headers["location"])
    assert "Only an active sprint can be completed." in page.text


def test_completing_an_empty_sprint_reports_nothing_to_carry(
    client: TestClient,
    project: Json,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Now"},
    ).json()
    client.post(f"/api/v1/sprints/{sprint['id']}/start")

    response = client.post(
        f"/web/sprints/{sprint['id']}/complete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "notice=" in response.headers["location"]
    page = client.get(response.headers["location"])
    assert "No unfinished issues to carry." in page.text


def test_completing_with_unfinished_work_returns_them_to_the_backlog(
    client: TestClient,
    project: Json,
) -> None:
    current = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Now"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "One", "sprint_id": current["id"]},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Two", "sprint_id": current["id"]},
    )
    client.post(f"/api/v1/sprints/{current['id']}/start")

    response = client.post(
        f"/web/sprints/{current['id']}/complete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "2 unfinished issues returned to the backlog." in page.text


def test_completing_a_sprint_reports_the_carry_over(
    client: TestClient,
    project: Json,
) -> None:
    current = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Now"},
    ).json()
    nxt = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Next", "starts_on": "2026-10-01"},
    ).json()
    assert nxt["name"] == "Next"
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Carry me", "sprint_id": current["id"]},
    )
    client.post(f"/api/v1/sprints/{current['id']}/start")

    response = client.post(
        f"/web/sprints/{current['id']}/complete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "notice=" in response.headers["location"]
    page = client.get(response.headers["location"])
    assert "moved to Next" in page.text
    assert nxt["name"] == "Next"


def test_the_project_nav_names_backlog_and_sprints(
    client: TestClient,
    project: Json,
) -> None:
    header = (
        client.get("/projects/KEEL")
        .text.split("<header", 1)[1]
        .split("</header>", 1)[0]
    )
    assert 'href="/projects/KEEL/backlog"' in header
    assert 'href="/projects/KEEL/sprints"' in header
    assert "Backlog" in header
    assert "Sprints" in header


def test_the_sprints_page_shows_auto_sprint_status(
    client: TestClient,
    project: Json,
) -> None:
    client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"sprint_cadence": "weekly"},
    )
    page = client.get("/projects/KEEL/sprints")
    assert "Auto-sprint is on (Weekly)" in page.text
    assert "Next close:" in page.text


def test_the_sprints_page_catches_up_an_overdue_window(
    client: TestClient,
    project: Json,
) -> None:
    client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"sprint_cadence": "weekly"},
    )
    active = client.get(
        f"/api/v1/projects/{project['id']}/sprints",
        params={"state": "active"},
    ).json()[0]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.patch(
        f"/api/v1/sprints/{active['id']}",
        json={"starts_on": yesterday, "ends_on": yesterday},
    )

    page = client.get("/projects/KEEL/sprints")
    assert "Opened" in page.text
    assert "automatically" in page.text
    listed = client.get(
        f"/api/v1/projects/{project['id']}/sprints",
        params={"state": "completed"},
    ).json()
    assert listed[0]["id"] == active["id"]
