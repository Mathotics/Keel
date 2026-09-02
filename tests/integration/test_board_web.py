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


def test_the_board_page_renders_every_column(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Ready"},
    )

    page = client.get("/projects/KEEL/board")

    assert page.status_code == 200
    assert "To Do" in page.text
    assert "In Progress" in page.text
    assert "KEEL-1" in page.text
    assert "Ready" in page.text
    assert 'action="/web/issues/' in page.text
    assert ">Move<" in page.text
    assert 'src="/assets/js/board.js"' in page.text


def test_the_type_filter_changes_what_the_board_queries(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "epic", "title": "Epic work"},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Story work"},
    )

    page = client.get("/projects/KEEL/board", params={"type": "epic"})

    assert "Epic work" in page.text
    assert "Story work" not in page.text
    assert 'value="epic" checked' in page.text or 'value="epic"checked' in page.text


def test_the_assignee_filter_changes_what_the_board_queries(
    client: TestClient,
    project: Json,
) -> None:
    ada = client.post("/api/v1/users", json={"display_name": "Ada"}).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Assigned to Ada", "assignee_id": ada["id"]},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Unassigned work"},
    )

    assigned = client.get("/projects/KEEL/board", params={"assignee": ada["id"]})
    open_only = client.get("/projects/KEEL/board", params={"assignee": "unassigned"})

    assert assigned.status_code == 200
    assert "Assigned to Ada" in assigned.text
    assert "Unassigned work" not in assigned.text
    assert f'value="{ada["id"]}" selected' in assigned.text or (
        f'value="{ada["id"]}"selected' in assigned.text
    )

    assert "Unassigned work" in open_only.text
    assert "Assigned to Ada" not in open_only.text
    assert 'value="unassigned" selected' in open_only.text or (
        'value="unassigned"selected' in open_only.text
    )
    assert 'name="assignee"' in client.get("/projects/KEEL/board").text


def test_the_sprint_filter_changes_what_the_board_queries(
    client: TestClient,
    project: Json,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Sprint 1"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "In sprint", "sprint_id": sprint["id"]},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Waiting"},
    )

    scheduled = client.get("/projects/KEEL/board", params={"sprint": sprint["id"]})
    waiting = client.get("/projects/KEEL/board", params={"sprint": "unscheduled"})

    assert scheduled.status_code == 200
    assert "In sprint" in scheduled.text
    assert "Waiting" not in scheduled.text
    assert f'value="{sprint["id"]}" selected' in scheduled.text or (
        f'value="{sprint["id"]}"selected' in scheduled.text
    )

    assert "Waiting" in waiting.text
    assert "In sprint" not in waiting.text
    assert 'value="unscheduled" selected' in waiting.text or (
        'value="unscheduled"selected' in waiting.text
    )
    page = client.get("/projects/KEEL/board")
    assert 'name="sprint"' in page.text
    assert "Any sprint" in page.text
    assert "Sprint 1" in page.text


def test_the_board_filter_keeps_apply_without_javascript(
    client: TestClient,
    project: Json,
) -> None:
    page = client.get("/projects/KEEL/board")
    assert "data-keel-autosubmit" in page.text
    assert "keel-autosubmit__fallback" in page.text
    assert ">Apply<" in page.text


def test_the_fallback_form_moves_a_card(
    client: TestClient,
    project: Json,
) -> None:
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Ready"},
    ).json()

    response = client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/projects/KEEL/board"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/projects/KEEL/board"
    moved = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert moved["status"] == "in_progress"


def test_a_move_survives_a_reload(client: TestClient, project: Json) -> None:
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Ready"},
    ).json()
    client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "blocked"})

    page = client.get("/projects/KEEL/board")
    blocked = page.text.split('data-status="blocked"', 1)[1].split(
        "data-status=",
        1,
    )[0]

    assert "KEEL-1" in blocked
    assert "Ready" in blocked


def test_the_project_page_links_to_the_board(
    client: TestClient,
    project: Json,
) -> None:
    page = client.get("/projects/KEEL")
    assert 'href="/projects/KEEL/board"' in page.text


def test_the_top_bar_names_the_board_inside_a_project(
    client: TestClient,
    project: Json,
) -> None:
    header = (
        client.get("/projects/KEEL/board")
        .text.split("<header", 1)[1]
        .split(
            "</header>",
            1,
        )[0]
    )
    assert 'href="/projects/KEEL/board"' in header
    assert 'href="/projects/KEEL/backlog"' in header
    assert 'href="/projects/KEEL/sprints"' in header
    assert "Board" in header


def test_board_script_hides_only_its_own_fallback(client: TestClient) -> None:
    """The picker script runs on every page, so it must not hide the Move form."""
    script = client.get("/assets/js/board.js")
    assert script.status_code == 200
    assert 'addEventListener("drop"' in script.text
    assert "data-keel-board" in script.text
    assert "/api/v1/issues/" in script.text

    css = client.get("/assets/brand.css").text
    hidden = css.split("[data-keel-board] .keel-card__fallback", 1)[1].split(
        "}",
        1,
    )[0]
    assert "display: none" in hidden


def test_an_unknown_project_board_is_not_found(client: TestClient) -> None:
    assert client.get("/projects/NOPE/board").status_code == 404
