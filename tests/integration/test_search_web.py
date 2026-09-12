from typing import Any

from fastapi.testclient import TestClient


def _project(client: TestClient) -> dict[str, Any]:
    created: dict[str, Any] = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    return created


def _issue(client: TestClient, project_id: int, **body: object) -> dict[str, Any]:
    payload = {"type": "story", "title": "Something", **body}
    response = client.post(f"/api/v1/projects/{project_id}/issues", json=payload)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_empty_find_does_not_open_results(client: TestClient) -> None:
    response = client.get("/search", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/projects"


def test_an_issue_key_jumps_from_the_bar(client: TestClient) -> None:
    project = _project(client)
    _issue(client, project["id"], title="Rework onboarding")
    response = client.get("/search", params={"q": "KEEL-1"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/issues/KEEL-1"


def test_a_project_key_jumps_from_the_bar(client: TestClient) -> None:
    _project(client)
    response = client.get("/search", params={"q": "KEEL"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/projects/KEEL"


def test_a_unique_user_name_jumps_to_users(client: TestClient) -> None:
    response = client.get("/search", params={"q": "Tester"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/users"


def test_title_matches_render_a_results_page(client: TestClient) -> None:
    project = _project(client)
    _issue(client, project["id"], title="Rework the onboarding script")
    page = client.get("/search", params={"q": "onboarding"})
    assert page.status_code == 200
    assert "KEEL-1" in page.text
    assert 'href="/issues/KEEL-1"' in page.text
    assert "Matches for “onboarding”" in page.text


def test_comment_matches_link_to_the_issue(client: TestClient) -> None:
    project = _project(client)
    issue = _issue(client, project["id"], title="Quiet")
    posted = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "the widget is stuck"},
    )
    assert posted.status_code == 201, posted.text
    page = client.get("/search", params={"q": "widget"})
    assert page.status_code == 200
    assert 'href="/issues/KEEL-1"' in page.text
    assert "widget" in page.text


def test_no_match_repeats_the_query(client: TestClient) -> None:
    page = client.get("/search", params={"q": "xyzzy"})
    assert page.status_code == 200
    assert "xyzzy" in page.text
    assert "None." in page.text


def test_global_results_name_the_project(client: TestClient) -> None:
    project = _project(client)
    _issue(client, project["id"], title="Shared word")
    page = client.get("/search", params={"q": "Shared"})
    assert page.status_code == 200
    assert "<th>Project</th>" in page.text
    assert "<td>KEEL</td>" in page.text


def test_scoped_results_omit_the_project_column(client: TestClient) -> None:
    project = _project(client)
    _issue(client, project["id"], title="Shared word")
    page = client.get("/search", params={"q": "Shared", "project": "KEEL"})
    assert page.status_code == 200
    assert "in KEEL" in page.text
    issues_block = page.text.split("<h2>Issues</h2>", 1)[1].split(
        "<h2>Projects</h2>", 1
    )[0]
    assert "<th>Project</th>" not in issues_block


def test_a_project_page_keeps_find_in_that_project(client: TestClient) -> None:
    _project(client)
    header = (
        client.get("/projects/KEEL")
        .text.split("<header", 1)[1]
        .split(
            "</header>",
            1,
        )[0]
    )
    find = header.split('class="keel-find"', 1)[1]
    assert 'name="project"' in find
    assert 'value="KEEL"' in find


def test_the_project_list_finds_globally(client: TestClient) -> None:
    header = (
        client.get("/projects").text.split("<header", 1)[1].split("</header>", 1)[0]
    )
    find = header.split('class="keel-find"', 1)[1]
    assert 'name="project"' not in find


def test_an_unknown_project_scope_still_searches(client: TestClient) -> None:
    page = client.get("/search", params={"q": "xyzzy", "project": "NOPE"})
    assert page.status_code == 200
    assert "xyzzy" in page.text
