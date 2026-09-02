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
