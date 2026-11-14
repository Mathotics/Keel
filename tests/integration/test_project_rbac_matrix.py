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

# Removed in the commit that enforces the route.
STILL_OPEN: frozenset[str] = frozenset(
    {
        "DELETE /api/v1/comments/{comment_id}",
        "DELETE /api/v1/dependencies/{dependency_id}",
        "DELETE /api/v1/series/{series_id}",
        "DELETE /api/v1/sprints/{sprint_id}",
        "GET /api/v1/issues/{issue_id}/comments",
        "GET /api/v1/issues/{issue_id}/dependencies",
        "GET /api/v1/projects/{project_id}",
        "GET /api/v1/projects/{project_id}/series",
        "GET /api/v1/projects/{project_id}/sprints",
        "GET /api/v1/series/{series_id}",
        "GET /api/v1/sprints/{sprint_id}",
        "GET /projects/{key}",
        "GET /projects/{key}/backlog",
        "GET /projects/{key}/board",
        "GET /projects/{key}/calendar",
        "GET /projects/{key}/gantt",
        "GET /projects/{key}/schedules",
        "GET /projects/{key}/schedules/{series_id}",
        "GET /projects/{key}/sprints",
        "GET /projects/{key}/sprints/{sprint_id}",
        "PATCH /api/v1/projects/{project_id}",
        "PATCH /api/v1/series/{series_id}",
        "PATCH /api/v1/sprints/{sprint_id}",
        "POST /api/v1/issues/{issue_id}/comments",
        "POST /api/v1/issues/{issue_id}/series",
        "POST /api/v1/projects/{project_id}/series",
        "POST /api/v1/projects/{project_id}/sprints",
        "POST /api/v1/series/{series_id}/pause",
        "POST /api/v1/series/{series_id}/resume",
        "POST /api/v1/sprints/{sprint_id}/complete",
        "POST /api/v1/sprints/{sprint_id}/start",
        "POST /web/comments/{comment_id}/delete",
        "POST /web/dependencies/{dependency_id}/delete",
        "POST /web/issues/{issue_id}/comments",
        "POST /web/issues/{issue_id}/dependencies",
        "POST /web/issues/{issue_id}/repeat",
        "POST /web/issues/{issue_id}/series",
        "POST /web/issues/{issue_id}/series-item",
        "POST /web/issues/{issue_id}/series-item/remove",
        "POST /web/projects/{project_id}/schedules",
        "POST /web/projects/{project_id}/sprints",
        "POST /web/projects/{project_id}/update",
        "POST /web/schedules/{series_id}/delete",
        "POST /web/schedules/{series_id}/pause",
        "POST /web/schedules/{series_id}/resume",
        "POST /web/schedules/{series_id}/update",
        "POST /web/sprints/{sprint_id}/complete",
        "POST /web/sprints/{sprint_id}/delete",
        "POST /web/sprints/{sprint_id}/start",
        "POST /web/sprints/{sprint_id}/update",
    }
)


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
    values = {
        "project_id": project_id,
        "key": "SECR",
        "issue_key": issue["key"],
        "user_id": outsider_id,
        "issue_id": issue["id"],
        "sprint_id": 0,
        "series_id": 0,
        "comment_id": 0,
        "dependency_id": 0,
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
