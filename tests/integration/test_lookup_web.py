from typing import Any

from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD

Json = dict[str, Any]


def test_lookup_routes_return_short_lists(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    home = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    first = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Take out trash", "labels": ["plumbing"]},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Quiet"},
    )
    client.post(
        f"/api/v1/projects/{home['id']}/issues",
        json={"type": "story", "title": "Take out recycling"},
    )

    scoped = client.get(
        "/web/lookup/issues",
        params={"q": "trash", "project": "KEEL", "exclude": first["id"]},
    )
    assert scoped.status_code == 200
    assert scoped.json() == []
    found = client.get("/web/lookup/issues", params={"q": "trash", "project": "KEEL"})
    assert found.json() == [
        {"id": first["id"], "key": "KEEL-1", "title": "Take out trash"},
    ]
    anywhere = client.get("/web/lookup/issues", params={"q": "take"})
    assert [row["key"] for row in anywhere.json()] == ["HOME-1", "KEEL-1"]
    missing = client.get(
        "/web/lookup/issues",
        params={"q": "trash", "project": "NOPE"},
    )
    assert missing.json() == []
    labels = client.get("/web/lookup/labels", params={"q": ""})
    assert labels.json() == ["unlabeled"]
    plumbing = client.get("/web/lookup/labels", params={"q": "plumb"})
    assert plumbing.json() == ["plumbing"]
    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada Lovelace", "password": TEST_PASSWORD},
    ).json()
    people = client.get("/web/lookup/users", params={"q": ""})
    assert people.json() == [{"id": None, "label": "Unassigned"}]
    found_person = client.get("/web/lookup/users", params={"q": "ada"})
    assert found_person.json() == [{"id": ada["id"], "label": "Ada Lovelace"}]


def test_a_parent_can_be_set_from_a_key_without_javascript(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    client.post(
        f"/web/projects/{project['id']}/issues",
        data={"type": "epic", "title": "Parent"},
        follow_redirects=False,
    )
    created = client.post(
        f"/web/projects/{project['id']}/issues",
        data={"type": "story", "title": "Story", "parent_query": "KEEL-1"},
        follow_redirects=False,
    )
    assert created.headers["location"] == "/issues/KEEL-2"
    story = client.get(f"/api/v1/projects/{project['id']}/issues").json()[1]
    assert story["parent_id"] is not None
    page = client.get("/issues/KEEL-2")
    assert 'value="KEEL-1 — Parent"' in page.text
    assert 'data-keel-lookup="issues"' in page.text
    assert 'name="parent_id"' not in page.text

    refused = client.post(
        f"/web/issues/{story['id']}/parent",
        data={"parent_query": "Parent"},
        follow_redirects=False,
    )
    assert "Choose+a+parent+issue" in refused.headers["location"]
    copied = client.post(
        f"/web/issues/{story['id']}/parent",
        data={"parent_query": "KEEL-1 — Parent"},
        follow_redirects=False,
    )
    assert copied.status_code == 303
    stored = client.get(f"/api/v1/issues/{story['id']}").json()
    assert stored["parent_id"] == story["parent_id"]


def test_a_link_can_be_added_from_a_key(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "First"},
    )
    second = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Second"},
    ).json()
    linked = client.post(
        f"/web/issues/{second['id']}/dependencies",
        data={"other_query": "KEEL-1", "relation": "blocks"},
        follow_redirects=False,
    )
    assert linked.headers["location"] == "/issues/KEEL-2"
    page = client.get("/issues/KEEL-2")
    assert "KEEL-1" in page.text
    assert 'name="other_query"' in page.text
    assert "No other issues to link." not in page.text
    missing = client.post(
        f"/web/issues/{second['id']}/dependencies",
        data={"other_query": "Second", "relation": "blocks"},
        follow_redirects=False,
    )
    assert "Choose+an+issue+to+link" in missing.headers["location"]


def test_an_unknown_board_label_is_refused(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Bare"},
    )
    page = client.get("/projects/KEEL/board", params={"label": "nope"})
    assert page.status_code == 200
    assert "Choose a label from the list." in page.text
    assert "Bare" in page.text
    assert 'value="nope"' in page.text
