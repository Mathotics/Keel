import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.domain.access import Permission, RoleCode
from keel.services import access as access_service
from keel.services import projects as project_service
from keel.services import users as user_service

ADA_PASSWORD = "ada-password-1"


def _ada(client: TestClient) -> dict[str, object]:
    created = client.post(
        "/api/v1/users",
        json={
            "display_name": "Ada",
            "username": "ada",
            "password": ADA_PASSWORD,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert isinstance(body, dict)
    return body


def _sign_in(client: TestClient, username: str, password: str) -> None:
    client.post("/logout")
    signed = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert signed.status_code == 303, signed.text


def test_a_member_is_forbidden_from_global_admin_pages(client: TestClient) -> None:
    _ada(client)
    _sign_in(client, "ada", ADA_PASSWORD)
    for path in ("/admin/log", "/admin/access", "/users"):
        response = client.get(path)
        assert response.status_code == 403, path
        assert "You are signed in, but this page is not allowed." in response.text
        assert 'href="/profile"' in response.text
        assert "/login" not in response.headers.get("location", "")
    assert "keel-admin" not in client.get("/").text
    refused = client.post(
        "/web/projects",
        data={"key": "NOPE", "name": "Nope"},
        follow_redirects=False,
    )
    assert refused.status_code == 403


def test_owner_manages_global_roles_and_direct_grants(client: TestClient) -> None:
    ada = _ada(client)
    page = client.get("/admin/access")
    assert page.status_code == 200
    assert "Access" in page.text
    assert "Ada" in page.text
    assert "Roles and permissions" in page.text
    assert "Permission dependencies" in page.text
    assert "Bypasses every global and project permission" in page.text
    assert "Requires View projects" in page.text
    log_tracker = re.search(
        r'<input type="checkbox" name="permission" value="view_log_tracker".*?/>',
        page.text,
        re.DOTALL,
    )
    assert log_tracker is not None
    assert 'data-requires="display_admin_menu"' in log_tracker.group(0)
    owner_panel = page.text.split("<h2>Tester</h2>", 1)[1].split("<h2>", 1)[0]
    permission_inputs = re.findall(
        r'<input type="checkbox" name="permission".*?/>',
        owner_panel,
        re.DOTALL,
    )
    assert len(permission_inputs) == 12
    assert all("checked" in box and "disabled" in box for box in permission_inputs)
    owner_member = re.search(
        r'<input type="checkbox" data-role="member".*?/>',
        owner_panel,
        re.DOTALL,
    )
    assert owner_member is not None
    assert "checked" not in owner_member.group(0)
    ada_panel = page.text.split("<h2>Ada</h2>", 1)[1].split("<h2>", 1)[0]
    ada_member = re.search(
        r'<input type="checkbox" data-role="member".*?/>',
        ada_panel,
        re.DOTALL,
    )
    assert ada_member is not None
    assert "checked" in ada_member.group(0)
    saved = client.put(
        f"/api/v1/access/global/{ada['id']}",
        json={"owner": False, "admin": False, "direct_permissions": ["create_users"]},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["roles"] == ["member"]
    assert set(body["direct_permissions"]) == {
        Permission.CREATE_USERS.value,
        Permission.VIEW_USERS.value,
    }
    _sign_in(client, "ada", ADA_PASSWORD)
    home = client.get("/").text
    nav = home.split('<nav class="keel-topbar__nav"', 1)[1].split("</nav>", 1)[0]
    admin = home.split('class="keel-admin"', 1)[1].split("</details>", 1)[0]
    assert 'href="/users"' not in nav
    assert 'href="/users"' in admin
    assert 'href="/admin/log"' not in admin
    assert client.get("/users").status_code == 200
    assert client.get("/admin/log").status_code == 403
    made_admin = client.put(
        f"/api/v1/access/global/{ada['id']}",
        json={"admin": True, "owner": False, "direct_permissions": []},
    )
    assert made_admin.status_code == 403


def test_an_admin_cannot_remove_the_last_owner(client: TestClient) -> None:
    ada = _ada(client)
    client.put(
        f"/api/v1/access/global/{ada['id']}",
        json={"admin": True, "owner": False, "direct_permissions": []},
    )
    _sign_in(client, "ada", ADA_PASSWORD)
    people = client.get("/api/v1/users").json()
    tester = next(person for person in people if person["display_name"] == "Tester")
    refused = client.put(
        f"/api/v1/access/global/{tester['id']}",
        json={"owner": False, "admin": True, "direct_permissions": []},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "access.owner_change"


def test_day_one_grants_name_the_existing_people(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user_service.create_user(session, "Jacob Hootman", "jacob_hootman", "x" * 12)
        user_service.create_user(session, "Cursor", "Cursor", "y" * 12)
        user_service.create_user(session, "Danielle", "danielle_hootman", "z" * 12)
        for key, name in (
            ("BOAT", "Boat"),
            ("HOUSE", "House"),
            ("KEEL", "Keel"),
            ("PERSONAL", "Personal"),
        ):
            project_service.create_project(session, key, name, "")
        access_service.assign_day_one(session)
        jacob = user_service.find_by_username(session, "jacob_hootman")
        cursor = user_service.find_by_username(session, "Cursor")
        danielle = user_service.find_by_username(session, "danielle_hootman")
        assert jacob is not None and cursor is not None and danielle is not None
        assert access_service.global_roles(session, jacob.id) == frozenset(
            {RoleCode.OWNER}
        )
        assert access_service.global_roles(session, cursor.id) == frozenset(
            {RoleCode.MEMBER}
        )
        assert access_service.global_roles(session, danielle.id) == frozenset(
            {RoleCode.MEMBER}
        )
        keel = project_service.get_project_by_key(session, "KEEL")
        house = project_service.get_project_by_key(session, "HOUSE")
        cursor_projects = access_service.load_access(session, cursor.id).project_ids
        danielle_projects = access_service.load_access(session, danielle.id).project_ids
        assert cursor_projects == frozenset({keel.id})
        assert danielle_projects == frozenset({house.id})
        session.rollback()
