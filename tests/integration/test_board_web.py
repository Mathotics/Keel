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


def _card_html(page_text: str, title: str) -> str:
    for chunk in page_text.split('class="keel-card"')[1:]:
        card = chunk.split("</article>", 1)[0]
        if title in card:
            return card
    raise AssertionError(f"No board card contained {title!r}")


def test_a_board_card_links_to_the_issue(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Ready"},
    )

    page = client.get("/projects/KEEL/board")
    card = page.text.split('class="keel-card"', 1)[1].split("</article>", 1)[0]
    assert 'class="keel-card__link"' in card
    assert 'href="/issues/KEEL-1"' in card
    assert 'draggable="false"' in card
    css = client.get("/assets/brand.css").text
    assert ".keel-card__link::after" in css
    assert "inset: 0" in css.split(".keel-card__link::after", 1)[1].split("}", 1)[0]


def test_board_cards_and_chips_use_type_colors(
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
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "subtask", "title": "Subtask work"},
    )

    page = client.get("/projects/KEEL/board")
    epic = _card_html(page.text, "Epic work")
    story = _card_html(page.text, "Story work")
    subtask = _card_html(page.text, "Subtask work")

    assert 'data-type="epic"' in epic
    assert 'data-type="story"' in story
    assert 'data-type="subtask"' in subtask
    assert 'class="keel-chip keel-type"' in epic
    assert 'class="keel-type" data-type="epic"' in page.text
    assert 'class="keel-type" data-type="story"' in page.text
    assert 'class="keel-type" data-type="subtask"' in page.text

    css = client.get("/assets/brand.css").text
    assert "--keel-type-epic: #0068b0" in css
    assert "--keel-type-story: #0f7a73" in css
    assert "--keel-type-subtask: #b86a00" in css
    assert ".keel-card[data-type]" in css
    assert ".keel-chip.keel-type[data-type]" in css


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
    assert "Cancelled" in page.text
    assert "KEEL-1" in page.text
    assert "Ready" in page.text
    assert "keel-priority--p4" in page.text
    assert ">P4<" in page.text
    assert 'action="/web/issues/' in page.text
    assert ">Move<" in page.text
    assert 'src="/assets/js/board.js"' in page.text


def test_a_story_card_links_to_its_epic_parent(
    client: TestClient,
    project: Json,
) -> None:
    epic = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "epic", "title": "Epic work"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Child story", "parent_id": epic["id"]},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Standalone"},
    )

    page = client.get("/projects/KEEL/board")
    child = _card_html(page.text, "Child story")
    standalone = _card_html(page.text, "Standalone")
    epic_card = _card_html(page.text, "Epic work")

    assert "Parent " in child
    assert 'class="keel-card__parent-link"' in child
    assert 'href="/issues/KEEL-1"' in child
    assert 'draggable="false"' in child.split("keel-card__parent-link", 1)[1]
    assert "No parent" not in child
    css = client.get("/assets/brand.css").text
    parent_rule = css.split(".keel-card__parent {")[-1].split("}", 1)[0]
    assert "z-index: 1" in parent_rule
    assert "Parent " not in standalone
    assert "keel-card__parent" not in standalone
    assert "Parent " not in epic_card
    assert "No parent" not in page.text


def test_a_subtask_card_links_to_its_story_parent(
    client: TestClient,
    project: Json,
) -> None:
    story = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Parent story"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "subtask", "title": "Child subtask", "parent_id": story["id"]},
    )

    page = client.get("/projects/KEEL/board")
    card = _card_html(page.text, "Child subtask")
    assert "Parent " in card
    assert 'href="/issues/KEEL-1"' in card.split("keel-card__parent-link", 1)[1]


def test_the_type_filter_still_shows_a_hidden_parent(
    client: TestClient,
    project: Json,
) -> None:
    epic = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "epic", "title": "Epic work"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Child story", "parent_id": epic["id"]},
    )

    page = client.get("/projects/KEEL/board", params={"type": "story"})
    card = _card_html(page.text, "Child story")

    assert "Epic work" not in page.text
    assert "Parent " in card
    assert 'href="/issues/KEEL-1"' in card


def test_separating_by_sprint_still_shows_a_parent_in_another_lane(
    client: TestClient,
    project: Json,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project['id']}/sprints",
        json={"name": "Sprint 1"},
    ).json()
    epic = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "epic", "title": "Epic work", "sprint_id": sprint["id"]},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Waiting child", "parent_id": epic["id"]},
    )

    page = client.get("/projects/KEEL/board", params={"by": "sprint"})
    first, rest = page.text.split("keel-board__lane-title", 1)[1].split(
        "keel-board__lane-title",
        1,
    )
    child = _card_html(rest, "Waiting child")

    assert "Sprint 1" in first
    assert "Epic work" in first
    assert "Waiting child" not in first
    assert "Unscheduled" in rest
    assert "Parent " in child
    assert 'href="/issues/KEEL-1"' in child


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


def test_separating_by_sprint_puts_cards_in_lanes(
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

    page = client.get("/projects/KEEL/board")
    assert page.status_code == 200
    assert "Separate by sprint" in page.text
    assert 'name="by" value="status"' in page.text
    assert 'name="by" value="sprint" checked' in page.text or (
        'name="by" value="sprint"checked' in page.text
    )
    assert 'class="keel-board__lane-title"' in page.text
    assert 'data-sprint-id="' in page.text

    first, rest = page.text.split("keel-board__lane-title", 1)[1].split(
        "keel-board__lane-title",
        1,
    )
    assert "Sprint 1" in first
    assert "In sprint" in first
    assert "Waiting" not in first
    assert "Unscheduled" in rest
    assert "Waiting" in rest
    assert "In sprint" not in rest

    explicit = client.get("/projects/KEEL/board", params={"by": "sprint"})
    assert 'class="keel-board__lane-title"' in explicit.text
    assert "Sprint 1" in explicit.text

    together = client.get("/projects/KEEL/board", params={"by": "status"})
    assert "keel-board__lane-title" not in together.text
    assert "data-sprint-id" not in together.text
    assert "In sprint" in together.text
    assert "Waiting" in together.text
    assert 'name="by" value="sprint"' in together.text
    assert 'name="by" value="sprint" checked' not in together.text
    assert 'name="by" value="sprint"checked' not in together.text


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


def test_the_board_shows_an_issue_own_estimate(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Sized", "estimate_minutes": 90},
    )
    page = client.get("/projects/KEEL/board")
    assert "1h 30m" in page.text
    assert "keel-card__estimate" in page.text


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
    assert "keel-card__link" in script.text
    assert "keel-card__parent-link" in script.text
    assert "data-keel-board" in script.text
    assert "/api/v1/issues/" in script.text
    assert "sprint_id" in script.text

    css = client.get("/assets/brand.css").text
    hidden = css.split("[data-keel-board] .keel-card__fallback", 1)[1].split(
        "}",
        1,
    )[0]
    assert "display: none" in hidden


def test_an_unknown_project_board_is_not_found(client: TestClient) -> None:
    assert client.get("/projects/NOPE/board").status_code == 404


def test_the_label_filter_changes_what_the_board_queries(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Tagged", "labels": ["urgent"]},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Bare"},
    )

    tagged = client.get("/projects/KEEL/board", params={"label": "urgent"})
    bare = client.get("/projects/KEEL/board", params={"label": "unlabeled"})
    assert "Tagged" in tagged.text
    assert "Bare" not in tagged.text
    assert 'class="keel-chip keel-label"' in tagged.text
    assert ">urgent<" in tagged.text
    assert "Bare" in bare.text
    assert "Tagged" not in bare.text
    page = client.get("/projects/KEEL/board")
    assert "Any label" in page.text
    assert "Unlabeled" in page.text


def test_the_master_board_is_reachable_without_a_project(client: TestClient) -> None:
    header = client.get("/").text.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'href="/board"' in header
    assert "Board" in header.split("<nav", 1)[1].split("</nav>", 1)[0]
    page = client.get("/board")
    assert page.status_code == 200
    assert "<h1>Board</h1>" in page.text
    assert "Nothing to show yet." in page.text
    assert 'href="/projects"' in page.text
    header = page.text.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'href="/projects/KEEL/backlog"' not in header


def test_the_master_board_mixes_projects_and_hides_completed_sprint_closed_work(
    client: TestClient,
) -> None:
    keel = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"}).json()
    house = client.post(
        "/api/v1/projects",
        json={"key": "HOUSE", "name": "House"},
    ).json()
    past = client.post(
        f"/api/v1/projects/{keel['id']}/sprints",
        json={"name": "Past"},
    ).json()
    finished = client.post(
        f"/api/v1/projects/{keel['id']}/issues",
        json={"type": "story", "title": "Finished past", "sprint_id": past["id"]},
    ).json()
    client.patch(f"/api/v1/issues/{finished['id']}", json={"status": "done"})
    client.post(f"/api/v1/sprints/{past['id']}/start")
    client.post(f"/api/v1/sprints/{past['id']}/complete")
    client.post(
        f"/api/v1/projects/{keel['id']}/issues",
        json={"type": "story", "title": "Keel work"},
    )
    client.post(
        f"/api/v1/projects/{house['id']}/issues",
        json={"type": "story", "title": "House work"},
    )

    page = client.get("/board")
    assert page.status_code == 200
    assert "Keel work" in page.text
    assert "House work" in page.text
    assert "Finished past" not in page.text
    assert "Finished past" in client.get("/projects/KEEL/board").text
    assert "Any project" in page.text
    assert 'name="project"' in page.text
    assert "HOUSE / " in page.text or "KEEL / " in page.text
    header = page.text.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'href="/board"' in header
    find = header.split("keel-find", 1)[1].split("</form>", 1)[0]
    assert 'name="project"' not in find


def test_the_master_board_project_filter_and_prefixed_sprint_lanes(
    client: TestClient,
) -> None:
    keel = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"}).json()
    house = client.post(
        "/api/v1/projects",
        json={"key": "HOUSE", "name": "House"},
    ).json()
    keel_sprint = client.post(
        f"/api/v1/projects/{keel['id']}/sprints",
        json={"name": "Sprint 1"},
    ).json()
    house_sprint = client.post(
        f"/api/v1/projects/{house['id']}/sprints",
        json={"name": "Sprint 1"},
    ).json()
    client.post(
        f"/api/v1/projects/{keel['id']}/issues",
        json={"type": "story", "title": "Keel card", "sprint_id": keel_sprint["id"]},
    )
    client.post(
        f"/api/v1/projects/{house['id']}/issues",
        json={"type": "story", "title": "House card", "sprint_id": house_sprint["id"]},
    )

    filtered = client.get("/board", params={"project": "HOUSE"})
    assert "House card" in filtered.text
    assert "Keel card" not in filtered.text
    assert 'value="HOUSE" selected' in filtered.text or (
        'value="HOUSE"selected' in filtered.text
    )
    assert "HOUSE / Sprint 1" in filtered.text
    assert "KEEL / Sprint 1" not in filtered.text

    lanes = client.get("/board", params={"by": "sprint"})
    assert "HOUSE / Sprint 1" in lanes.text
    assert "KEEL / Sprint 1" in lanes.text
    assert 'data-sprint-id="' in lanes.text


def test_the_fallback_form_returns_to_the_master_board(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Ready"},
    ).json()
    response = client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/board"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/board"
