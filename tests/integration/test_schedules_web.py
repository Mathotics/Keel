from fastapi.testclient import TestClient


def _series_payload(**overrides: str) -> dict[str, str]:
    body: dict[str, str] = {
        "title": "Take out trash",
        "type": "story",
        "spawn_mode": "calendar",
        "sprint_basis": "due_on",
        "freq": "weekly",
        "interval": "1",
        "starts_on": "2026-09-14",
        "weekday": "0",
        "look_ahead_n": "1",
        "end_mode": "never",
    }
    body.update(overrides)
    return body


def test_the_schedules_page_has_an_empty_state(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    page = client.get("/projects/HOME/schedules")
    assert page.status_code == 200
    assert "No repeating series." in page.text
    assert 'href="/projects/HOME/schedules"' in page.text.split("<header", 1)[1]
    assert 'href="/projects/HOME/schedules?tab=new"' in page.text
    assert "Create series" not in page.text
    form = client.get("/projects/HOME/schedules?tab=new")
    assert form.status_code == 200
    assert "Create series" in form.text
    assert 'name="title"' in form.text
    created = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(),
        follow_redirects=False,
    )
    assert created.status_code == 303
    listing = client.get("/projects/HOME/schedules")
    assert "Take out trash" in listing.text
    assert "Weekly on Mon" in listing.text
    detail = client.get(created.headers["location"])
    assert detail.status_code == 200
    assert "Pause" in detail.text
    assert "Stop" in detail.text
    assert "Save recipe" in detail.text


def test_a_refused_series_returns_to_the_new_series_tab(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    refused = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(title=""),
        follow_redirects=False,
    )
    assert refused.status_code == 303
    location = refused.headers["location"]
    assert location.startswith("/projects/HOME/schedules?tab=new")
    page = client.get(location)
    assert "Create series" in page.text
    assert "A series needs a title." in page.text


def test_a_series_can_be_paused_resumed_edited_and_stopped(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    created = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(),
        follow_redirects=False,
    )
    here = created.headers["location"]
    series_id = int(here.rsplit("/", 1)[1])
    paused = client.post(
        f"/web/schedules/{series_id}/pause",
        follow_redirects=False,
    )
    assert paused.status_code == 303
    page = client.get(here)
    assert "Paused" in page.text
    assert "Resume" in page.text
    client.post(f"/web/schedules/{series_id}/resume", follow_redirects=False)
    updated = client.post(
        f"/web/schedules/{series_id}/update",
        data=_series_payload(title="Bin night", interval="2"),
        follow_redirects=False,
    )
    assert updated.status_code == 303
    page = client.get(here)
    assert "Bin night" in page.text
    assert "Every 2 weeks on Mon" in page.text
    client.post(f"/web/schedules/{series_id}/stop", follow_redirects=False)
    page = client.get(here)
    assert "Stopped" in page.text
    assert "Save recipe" not in page.text
    assert "the recipe cannot change" in page.text


def test_an_issue_can_become_a_series_and_show_on_the_board(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Pay bills"},
    ).json()
    client.post(
        f"/web/issues/{issue['id']}/repeat",
        data={
            "spawn_mode": "after_closed",
            "sprint_basis": "due_on",
            "freq": "monthly",
            "interval": "1",
            "starts_on": "2026-09-01",
            "month_day": "1",
            "look_ahead_n": "1",
            "end_mode": "never",
        },
        follow_redirects=False,
    )
    detail = client.get(f"/issues/{issue['key']}")
    assert "Repeating series" in detail.text
    assert "This occurrence" in detail.text
    assert "Delete this issue to skip this cycle" in detail.text
    assert "Pay bills" in detail.text
    board = client.get("/projects/HOME/board")
    assert "Pay bills" in board.text
    backlog = client.get("/projects/HOME/backlog")
    assert "Pay bills" in backlog.text
    search = client.get("/search", params={"q": "Pay bills", "project": "HOME"})
    assert search.status_code == 200
    assert issue["key"] in search.text
    client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "cancelled", "next": f"/issues/{issue['key']}"},
        follow_redirects=False,
    )
    issues = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    assert len(issues) >= 2
    assert any(item["status"] == "cancelled" for item in issues)
    assert any(
        item["status"] == "todo" and item["series_id"] is not None for item in issues
    )


def test_outlook_edit_and_skip_stay_on_the_issue_page(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    created = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(look_ahead_n="2"),
        follow_redirects=False,
    )
    series_id = int(created.headers["location"].rsplit("/", 1)[1])
    issues = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    copies = [item for item in issues if item["series_id"] == series_id]
    copies.sort(key=lambda item: item["occurrence_on"] or "")
    first = copies[0]
    scoped = client.post(
        f"/web/issues/{first['id']}/series",
        data=_series_payload(title="This week only", scope="this"),
        follow_redirects=False,
    )
    assert scoped.status_code == 303
    page = client.get(f"/issues/{first['key']}")
    assert "This week only" in page.text
    recipe = client.get(created.headers["location"])
    assert "Take out trash" in recipe.text
    skipped = client.post(
        f"/web/issues/{first['id']}/delete",
        follow_redirects=False,
    )
    assert skipped.status_code == 303
    remaining = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    assert first["id"] not in {item["id"] for item in remaining}
    board = client.get("/projects/HOME/board")
    assert "This week only" not in board.text
    assert "Take out trash" in board.text


def test_spawned_issues_show_on_the_sprint_page(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={
            "name": "This week",
            "starts_on": "2026-09-12",
            "ends_on": "2026-09-18",
        },
    ).json()
    client.post(f"/api/v1/sprints/{sprint['id']}/start")
    client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(),
        follow_redirects=False,
    )
    page = client.get(f"/projects/HOME/sprints/{sprint['id']}")
    assert page.status_code == 200
    assert "Take out trash" in page.text
    listing = client.get("/projects/HOME/sprints")
    assert "This week" in listing.text
