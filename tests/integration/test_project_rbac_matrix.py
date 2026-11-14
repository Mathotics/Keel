"""Every project route denies an outsider and a No Access user.

Routes still waiting on a later KEEL-181 story are listed in ``STILL_OPEN``.
A new project route that is not in that set, and not intentionally open, has
to answer 403 or this test fails.
"""

import re
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

_MARKERS = (
    "{project_id}",
    "{issue_id}",
    "{sprint_id}",
    "{series_id}",
    "{comment_id}",
    "{dependency_id}",
)

# A project-shaped route that stays available on purpose. Empty until a story
# records that decision.
INTENTIONALLY_OPEN: frozenset[str] = frozenset()

# Removed in the commit that enforces the route. Empty once every project
# route checks a permission.
STILL_OPEN: frozenset[str] = frozenset()


def project_route_ids(app: FastAPI) -> set[str]:
    """Public method and path of every project route.

    FastAPI keeps included routers nested, so the walk follows each mount
    instead of reading only the routes hung directly on the app.
    """
    found: set[str] = set()
    for path, methods in _walk(app.routes, ""):
        if not _is_project_route(path):
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            found.add(f"{method} {path}")
    return found


def _walk(routes: object, prefix: str) -> list[tuple[str, set[str]]]:
    found: list[tuple[str, set[str]]] = []
    if not isinstance(routes, list):
        return found
    for route in routes:
        if isinstance(route, APIRoute):
            found.append((_join(prefix, route.path), set(route.methods or ())))
            continue
        if type(route).__name__ != "_IncludedRouter":
            continue
        mounted = prefix
        context = getattr(route, "include_context", None)
        mounted_prefix = getattr(context, "prefix", "") or ""
        if mounted_prefix:
            mounted = mounted_prefix
        original = getattr(route, "original_router", None)
        found.extend(_walk(getattr(original, "routes", []), mounted))
    return found


def _join(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if path == prefix or path.startswith(prefix + "/"):
        return path
    if path == "/":
        return prefix or "/"
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _is_project_route(path: str) -> bool:
    if any(marker in path for marker in _MARKERS):
        return True
    if "{key}" in path and "/projects" in path:
        return True
    return path.startswith("/issues/{key}")


def test_every_project_route_is_accounted_for(app: FastAPI) -> None:
    found = project_route_ids(app)
    stale = (STILL_OPEN | INTENTIONALLY_OPEN) - found
    assert not stale, f"allowlist names routes that are gone: {sorted(stale)}"


def test_guarded_project_routes_deny_outsiders_and_no_access(
    client: TestClient,
    app: FastAPI,
) -> None:
    guarded = sorted(
        project_route_ids(app) - STILL_OPEN - INTENTIONALLY_OPEN,
    )
    project = client.post(
        "/api/v1/projects",
        json={"key": "SECR", "name": "Secret"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    outsider_id = _user(client, "Outsider", "outsider", "outsider@example.com")
    mallory_id = _user(client, "Mallory", "mallory", "mallory@example.com")
    refused = client.put(
        f"/api/v1/access/global/{mallory_id}",
        json={"no_access": True, "direct_permissions": []},
    )
    assert refused.status_code == 200, refused.text
    created_issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Hidden"},
    )
    assert created_issue.status_code == 201, created_issue.text
    issue = created_issue.json()
    other_issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Also hidden"},
    )
    assert other_issue.status_code == 201, other_issue.text
    link = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": issue["id"],
            "target_id": other_issue.json()["id"],
            "kind": "blocks",
        },
    )
    assert link.status_code == 201, link.text
    note = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "secret"},
    )
    assert note.status_code == 201, note.text
    sprint = client.post(
        f"/api/v1/projects/{project_id}/sprints",
        json={"name": "Hidden sprint"},
    )
    assert sprint.status_code == 201, sprint.text
    series = client.post(
        f"/api/v1/projects/{project_id}/series",
        json={
            "title": "Hidden schedule",
            "type": "story",
            "spawn_mode": "calendar",
            "sprint_basis": "created_on",
            "freq": "daily",
            "starts_on": "2026-09-12",
        },
    )
    assert series.status_code == 201, series.text
    values = {
        "project_id": project_id,
        "key": "SECR",
        "issue_key": issue["key"],
        "user_id": outsider_id,
        "issue_id": issue["id"],
        "sprint_id": sprint.json()["id"],
        "series_id": series.json()["id"],
        "comment_id": note.json()["id"],
        "dependency_id": link.json()["id"],
        "label_id": 0,
    }

    for username, password in (
        ("outsider", "person-password-1"),
        ("mallory", "person-password-1"),
    ):
        _sign_in(client, username, password)
        for route_id in guarded:
            response = _call(client, route_id, values)
            assert response.status_code == 403, (username, route_id, response.text)


def _user(client: TestClient, display_name: str, username: str, email: str) -> int:
    created = client.post(
        "/api/v1/users",
        json={
            "display_name": display_name,
            "username": username,
            "password": "person-password-1",
            "email": email,
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert isinstance(user_id, int)
    return user_id


def _sign_in(client: TestClient, username: str, password: str) -> None:
    client.post("/logout")
    signed = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert signed.status_code == 303, signed.text


def test_home_omits_issues_from_projects_the_user_cannot_view(
    client: TestClient,
) -> None:
    open_project = client.post(
        "/api/v1/projects",
        json={"key": "OPEN", "name": "Open"},
    )
    hidden_project = client.post(
        "/api/v1/projects",
        json={"key": "HIDE", "name": "Hidden"},
    )
    assert open_project.status_code == 201, open_project.text
    assert hidden_project.status_code == 201, hidden_project.text
    person_id = _user(client, "Riley", "riley", "riley@example.com")
    _project_role(client, open_project.json()["id"], person_id, "viewer")
    visible = client.post(
        f"/api/v1/projects/{open_project.json()['id']}/issues",
        json={"type": "story", "title": "Shown", "assignee_id": person_id},
    )
    hidden = client.post(
        f"/api/v1/projects/{hidden_project.json()['id']}/issues",
        json={"type": "story", "title": "Secret", "assignee_id": person_id},
    )
    assert visible.status_code == 201, visible.text
    assert hidden.status_code == 201, hidden.text

    _sign_in(client, "riley", "person-password-1")
    home = client.get("/")
    assert home.status_code == 200, home.text
    assert visible.json()["key"] in home.text
    assert hidden.json()["key"] not in home.text
    assert client.get("/projects/OPEN").status_code == 200
    assert client.get("/projects/HIDE").status_code == 403
    assert client.get("/projects/HIDE/board").status_code == 403
    assert client.get("/projects/OPEN/calendar").status_code == 200


def test_search_lookup_and_labels_hide_other_projects(client: TestClient) -> None:
    open_project = client.post(
        "/api/v1/projects",
        json={"key": "OPEN", "name": "Open"},
    )
    hidden_project = client.post(
        "/api/v1/projects",
        json={"key": "HIDE", "name": "Hidden"},
    )
    assert open_project.status_code == 201, open_project.text
    assert hidden_project.status_code == 201, hidden_project.text
    open_id = open_project.json()["id"]
    hidden_id = hidden_project.json()["id"]
    person_id = _user(client, "Riley", "riley", "riley@example.com")
    _project_role(client, open_id, person_id, "viewer")
    shown = client.post(
        f"/api/v1/projects/{open_id}/issues",
        json={"type": "story", "title": "Shown work", "labels": ["public"]},
    )
    secret = client.post(
        f"/api/v1/projects/{hidden_id}/issues",
        json={"type": "story", "title": "Secret work", "labels": ["covert"]},
    )
    sprint = client.post(
        f"/api/v1/projects/{hidden_id}/sprints",
        json={"name": "Covert sprint"},
    )
    assert shown.status_code == 201, shown.text
    assert secret.status_code == 201, secret.text
    assert sprint.status_code == 201, sprint.text
    secret_key = secret.json()["key"]

    _sign_in(client, "riley", "person-password-1")
    assert client.get(f"/api/v1/projects/{hidden_id}").status_code == 403
    assert client.get(f"/api/v1/projects/{open_id}").status_code == 200

    hidden_jump = client.get("/api/v1/search", params={"q": secret_key})
    assert hidden_jump.status_code == 200, hidden_jump.text
    assert hidden_jump.json()["kind"] == "results"
    assert hidden_jump.json()["issues"] == []
    assert hidden_jump.json()["projects"] == []
    named = client.get("/api/v1/search", params={"q": "Hidden"})
    assert named.json()["projects"] == []
    assert named.json()["issues"] == []
    visible = client.get("/api/v1/search", params={"q": shown.json()["key"]})
    assert visible.json()["kind"] == "jump"
    assert visible.json()["key"] == shown.json()["key"]

    page = client.get("/search", params={"q": secret_key}, follow_redirects=False)
    assert page.status_code == 200, page.text
    assert f'/issues/{secret_key}"' not in page.text

    names = [item["name"] for item in client.get("/api/v1/labels").json()]
    assert "public" in names
    assert "covert" not in names
    assert client.get("/web/lookup/projects", params={"q": "hid"}).json() == []
    assert client.get("/web/lookup/issues", params={"q": "secret"}).json() == []
    assert "covert" not in client.get("/web/lookup/labels", params={"q": "cov"}).json()

    calendar = client.get("/calendar")
    assert calendar.status_code == 200, calendar.text
    assert "Covert sprint" not in calendar.text
    filtered = client.get("/calendar", params={"project": "HIDE"})
    assert filtered.status_code == 200, filtered.text
    assert "Hidden" not in filtered.text

    detail = client.get(f"/issues/{shown.json()['key']}")
    assert detail.status_code == 200, detail.text
    assert "covert" not in detail.text
    assert "public" in detail.text


def test_project_role_gates_issue_reads_and_writes(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "ROLE", "name": "Roles"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    created = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Visible"},
    )
    assert created.status_code == 201, created.text
    issue_id = created.json()["id"]
    issue_key = created.json()["key"]
    person_id = _user(client, "Riley", "riley", "riley@example.com")
    _project_role(client, project_id, person_id, "viewer")

    _sign_in(client, "riley", "person-password-1")
    read = client.get(f"/api/v1/issues/{issue_id}")
    assert read.status_code == 200, read.text
    page = client.get(f"/issues/{issue_key}")
    assert page.status_code == 200, page.text
    assert "Delete issue" not in page.text
    patched = client.patch(f"/api/v1/issues/{issue_id}", json={"title": "Nope"})
    assert patched.status_code == 403, patched.text
    created_denied = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Nope"},
    )
    assert created_denied.status_code == 403, created_denied.text

    _sign_in(client, "Tester", "tester-password")
    _project_role(client, project_id, person_id, "contributor")
    _sign_in(client, "riley", "person-password-1")
    edited = client.patch(f"/api/v1/issues/{issue_id}", json={"title": "Edited"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Edited"
    deleted = client.delete(f"/api/v1/issues/{issue_id}")
    assert deleted.status_code == 403, deleted.text

    _sign_in(client, "Tester", "tester-password")
    editor = client.put(
        f"/api/v1/access/global/{person_id}",
        json={"editor": True, "direct_permissions": []},
    )
    assert editor.status_code == 200, editor.text
    _project_role(client, project_id, person_id, "project_owner")
    _sign_in(client, "riley", "person-password-1")
    removed = client.delete(f"/api/v1/issues/{issue_id}")
    assert removed.status_code == 204, removed.text


def _project_role(
    client: TestClient,
    project_id: int,
    user_id: int,
    role: str,
) -> None:
    saved = client.post(
        f"/web/projects/{project_id}/access/{user_id}",
        data={"role": role},
        follow_redirects=False,
    )
    assert saved.status_code == 303, saved.text


def _call(client: TestClient, route_id: str, values: dict[str, object]) -> Any:
    method, path = route_id.split(" ", 1)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "key" and path.startswith("/issues/"):
            name = "issue_key"
        return str(values[name])

    concrete = re.sub(r"\{([^}]+)\}", replace, path)
    if method not in {"POST", "PUT", "PATCH"}:
        return client.request(method, concrete, follow_redirects=False)
    if path.startswith("/api/"):
        return client.request(method, concrete, json={}, follow_redirects=False)
    return client.request(method, concrete, data={}, follow_redirects=False)
