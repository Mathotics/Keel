from urllib.parse import parse_qs, urlparse

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


def _overlay_is_open(html: str) -> bool:
    opening = html.split('id="issue-repeat-overlay"', 1)[1].split(">", 1)[0]
    return " open" in opening


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
    assert "Start offset (days before occurrence)" in form.text
    assert "Due offset (days after occurrence)" in form.text
    assert 'name="title"' in form.text
    assert 'name="priority"' in form.text
    assert 'value="p4" selected' in form.text
    assert "P4 — Minor" in form.text
    cadence = form.text.split("<legend>Cadence</legend>", 1)[1].split("</fieldset>", 1)[
        0
    ]
    assert cadence.index('name="month_day"') < cadence.index('name="month"')
    assert cadence.index('name="month"') < cadence.index('name="nth_week"')
    assert '<select id="series-month" name="month">' in cadence
    assert "From start date" in cadence
    assert '<option value="1"' in cadence and "January" in cadence
    assert '<option value="12"' in cadence and "December" in cadence
    created = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(),
        follow_redirects=False,
    )
    assert created.status_code == 303
    listing = client.get("/projects/HOME/schedules")
    assert "Take out trash" in listing.text
    assert "Weekly on Mon" in listing.text
    assert "P4 — Minor" in listing.text
    detail = client.get(created.headers["location"])
    assert detail.status_code == 200
    assert "Pause" in detail.text
    assert "Delete" in detail.text
    assert "Stop" not in detail.text
    assert "Save recipe" in detail.text


def test_a_series_can_set_priority_for_spawned_copies(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    created = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(priority="p1"),
        follow_redirects=False,
    )
    assert created.status_code == 303
    listing = client.get("/projects/HOME/schedules")
    assert "P1 — Blocker" in listing.text
    page = client.get(created.headers["location"])
    assert '<option value="p1" selected>P1 — Blocker</option>' in page.text
    series_id = int(created.headers["location"].rsplit("/", 1)[1])
    copies = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    spawned = [item for item in copies if item["series_id"] == series_id]
    assert spawned
    assert {item["priority"] for item in spawned} == {"p1"}


def test_a_yearly_series_keeps_the_chosen_month(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    created = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(
            freq="yearly",
            starts_on="2026-02-01",
            month="2",
            month_day="1",
        ),
        follow_redirects=False,
    )
    assert created.status_code == 303
    page = client.get(created.headers["location"])
    assert page.status_code == 200
    assert "Yearly on 1 Feb" in page.text
    cadence = page.text.split("<legend>Cadence</legend>", 1)[1].split("</fieldset>", 1)[
        0
    ]
    assert '<option value="2" selected>February</option>' in cadence


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


def test_a_negative_start_offset_is_refused(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    refused = client.post(
        f"/web/projects/{project['id']}/schedules",
        data=_series_payload(start_offset_days="-1"),
        follow_redirects=False,
    )
    assert refused.status_code == 303
    location = refused.headers["location"]
    assert location.startswith("/projects/HOME/schedules?tab=new")
    page = client.get(location)
    assert "Day offset cannot be negative." in page.text
    listing = client.get("/projects/HOME/schedules")
    assert "Take out trash" not in listing.text


def test_a_series_can_be_paused_resumed_edited_and_deleted(
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
    issues = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    copies = [item for item in issues if item["series_id"] == series_id]
    assert copies
    deleted = client.post(
        f"/web/schedules/{series_id}/delete",
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert deleted.headers["location"].startswith("/projects/HOME/schedules")
    listing = client.get(deleted.headers["location"])
    assert "Bin night" not in listing.text
    assert "Schedule deleted. Existing issues remain." in listing.text
    remaining = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    assert {item["id"] for item in copies} <= {item["id"] for item in remaining}
    first = remaining[0]
    assert first["series_id"] is None
    assert first["former_series_title"] == "Bin night"
    assert first["former_series_cadence"] == "Every 2 weeks on Mon"
    board = client.get("/projects/HOME/board")
    assert first["key"] in board.text
    assert first["title"] in board.text
    detail = client.get(f"/issues/{first['key']}")
    assert "The recipe is gone." in detail.text
    assert "Every 2 weeks on Mon" in detail.text
    assert "Make this repeating" in detail.text
    assert "Save series" not in detail.text
    missing = client.get(here)
    assert missing.status_code == 404


def test_an_issue_can_become_a_series_and_show_on_the_board(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Pay bills", "priority": "p2"},
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
    assert "Edit series" in detail.text
    assert "Make this repeating" not in detail.text
    assert "Delete this issue to skip this cycle" in detail.text
    assert "Pay bills" in detail.text
    assert 'href="/issues/' in detail.text and "?repeat=1" in detail.text
    assert not _overlay_is_open(detail.text)
    assert "This occurrence" in detail.text
    opened = client.get(f"/issues/{issue['key']}?repeat=1")
    assert _overlay_is_open(opened.text)
    assert "Save series" in opened.text
    assert '<option value="p2" selected>P2 — Critical</option>' in opened.text
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


def test_the_issue_recipe_stays_in_an_overlay(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Pay bills"},
    ).json()
    here = f"/issues/{issue['key']}"
    page = client.get(here)
    assert "Make this repeating" in page.text
    assert f'href="{here}?repeat=1"' in page.text
    assert 'src="/assets/js/overlay.js"' in page.text
    assert not _overlay_is_open(page.text)
    opened = client.get(f"{here}?repeat=1")
    assert _overlay_is_open(opened.text)
    assert "Make repeating" in opened.text
    closed = opened.text.split("<dialog", 1)[0]
    assert "Look-ahead N" not in closed

    refused = client.post(
        f"/web/issues/{issue['id']}/repeat",
        data={
            "spawn_mode": "calendar",
            "sprint_basis": "due_on",
            "freq": "weekly",
            "interval": "1",
            "starts_on": "",
            "look_ahead_n": "1",
            "end_mode": "never",
        },
        follow_redirects=False,
    )
    assert refused.status_code == 303
    location = refused.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["repeat"] == ["1"]
    assert query["error"] == ["A series needs a start date."]
    failed = client.get(location)
    assert _overlay_is_open(failed.text)
    overlay = failed.text.split('id="issue-repeat-overlay"', 1)[1]
    assert "A series needs a start date." in overlay.split("</dialog>", 1)[0]
    assert "keel-error" not in failed.text.split("<dialog", 1)[0]

    saved = client.post(
        f"/web/issues/{issue['id']}/repeat",
        data={
            "spawn_mode": "calendar",
            "sprint_basis": "due_on",
            "freq": "weekly",
            "interval": "1",
            "starts_on": "2026-09-14",
            "weekday": "0",
            "look_ahead_n": "1",
            "end_mode": "never",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == here
    after = client.get(here)
    assert "Edit series" in after.text
    assert not _overlay_is_open(after.text)

    scoped = client.post(
        f"/web/issues/{issue['id']}/series",
        data=_series_payload(title="", scope="series"),
        follow_redirects=False,
    )
    assert scoped.status_code == 303
    scoped_query = parse_qs(urlparse(scoped.headers["location"]).query)
    assert scoped_query["repeat"] == ["1"]
    assert "error" in scoped_query
    again = client.get(scoped.headers["location"])
    assert _overlay_is_open(again.text)
    assert "keel-error" in again.text.split('id="issue-repeat-overlay"', 1)[1]


def test_overlay_script_opens_without_a_framework(client: TestClient) -> None:
    script = client.get("/assets/js/overlay.js")
    assert script.status_code == 200
    assert "showModal" in script.text
    assert "data-keel-overlay-js" in script.text
    assert "data-keel-overlay-open" in script.text
    assert "data-keel-overlay-close" in script.text
    assert 'src="/assets/js/overlay.js"' not in client.get("/").text
