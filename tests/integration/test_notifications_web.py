from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.domain.enums import IssueType, NotificationType
from keel.services import issues as issue_service
from keel.services import notifications as notification_service
from keel.services import projects as project_service
from keel.services import users as user_service


def _right(html: str) -> str:
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    return header.split('class="keel-topbar__right"', 1)[1]


def _bell(html: str) -> str:
    right = _right(html)
    return right.split('class="keel-topbar__control keel-bell"', 1)[1].split(
        "</a>",
        1,
    )[0]


def _dot(html: str) -> str:
    at = html.index("data-keel-bell-dot")
    return html[at : html.index(">", at)]


def _unread(html: str, title: str) -> bool:
    for part in html.split('<article class="keel-notice')[1:]:
        chunk = part.split("</article>", 1)[0]
        if title in chunk:
            return chunk.startswith(" keel-notice--unread")
    raise AssertionError(title)


def _checked(html: str, name: str, value: str) -> bool:
    needle = f'name="{name}" value="{value}"'
    at = html.index(needle)
    tag = html[html.rfind("<input", 0, at) : html.index(">", at)]
    return "checked" in tag


def test_an_empty_inbox_has_no_dot_and_says_so(client: TestClient) -> None:
    page = client.get("/notifications")
    assert page.status_code == 200
    assert "There are no notifications." in page.text
    assert "hidden" in _dot(page.text)
    bell = _bell(page.text)
    assert 'aria-label="Notifications"' in bell
    assert ">Notifications<" not in bell
    assert "<svg" in bell
    assert not any(character.isdigit() for character in _dot(page.text))
    assert 'src="/assets/js/bell.js"' in page.text
    script = client.get("/assets/js/bell.js")
    assert script.status_code == 200
    assert "30000" in script.text
    assert "/api/v1/notifications" in script.text


def test_anonymous_notifications_go_to_sign_in(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.get("/notifications", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_the_bell_sits_left_of_help_when_admin_is_hidden(app: FastAPI) -> None:
    with TestClient(app) as ada_client:
        with app.state.session_factory() as session:
            ada = user_service.create_user(session, "Ada")
            user_service.set_password(session, ada, "tester-password")
            session.commit()
        signed = ada_client.post(
            "/login",
            data={"username": "Ada", "password": "tester-password"},
            follow_redirects=False,
        )
        assert signed.status_code == 303
        right = _right(ada_client.get("/profile").text)
    assert ">Admin<" not in right
    assert right.index("keel-bell") < right.index(">Help<")


def test_viewing_the_page_marks_notices_read_without_deleting_them(
    client: TestClient,
    app: FastAPI,
) -> None:
    me = client.get("/api/v1/profile").json()
    with app.state.session_factory() as session:
        ada = user_service.create_user(session, "Ada").id
        project = project_service.create_project(session, "KEEL", "Keel")
        issue = issue_service.create_issue(
            session,
            project.id,
            type=IssueType.STORY,
            title="Hull",
            reporter_id=me["id"],
        )
        key = issue_service.issue_key(issue, project)
        notification_service.add_notice(
            session,
            recipient_id=me["id"],
            notice_type=NotificationType.COMMENT_ON_CREATED,
            actor_id=ada,
            actor_name="Ada",
            issue_id=issue.id,
            issue_key=key,
            issue_title="Older hull",
            body="First",
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
        notification_service.add_notice(
            session,
            recipient_id=me["id"],
            notice_type=NotificationType.UPDATE_ON_CREATED,
            actor_id=ada,
            actor_name="Ada",
            issue_id=issue.id,
            issue_key=key,
            issue_title="Newer deck",
            body="Second",
            created_at=datetime(2026, 11, 8, tzinfo=UTC),
        )
        notification_service.add_notice(
            session,
            recipient_id=ada,
            notice_type=NotificationType.ASSIGNED,
            actor_name="Tester",
            issue_key="KEEL-9",
            issue_title="Private",
            body="Not yours",
        )
        session.commit()

    home = client.get("/")
    assert "hidden" not in _dot(home.text)
    listed = client.get("/api/v1/notifications").json()
    assert listed
    assert all(item["read_at"] is None for item in listed)
    assert "hidden" not in _dot(client.get("/").text)

    page = client.get("/notifications")
    assert "There are no notifications." not in page.text
    assert "Private" not in page.text
    assert page.text.index("Newer deck") < page.text.index("Older hull")
    assert not _unread(page.text, "Newer deck")
    assert not _unread(page.text, "Older hull")
    assert "First" in page.text
    assert "Second" in page.text
    assert "hidden" in _dot(page.text)
    assert "hidden" in _dot(client.get("/").text)
    kept = client.get("/api/v1/notifications").json()
    assert {item["issue_title"] for item in kept} == {"Newer deck", "Older hull"}
    assert all(item["read_at"] is not None for item in kept)


def test_opening_one_marks_only_that_notice_and_opens_the_issue(
    client: TestClient,
    app: FastAPI,
) -> None:
    me = client.get("/api/v1/profile").json()
    with app.state.session_factory() as session:
        project = project_service.create_project(session, "KEEL", "Keel")
        issue = issue_service.create_issue(
            session,
            project.id,
            type=IssueType.STORY,
            title="Hull",
            reporter_id=me["id"],
        )
        key = issue_service.issue_key(issue, project)
        opened = notification_service.add_notice(
            session,
            recipient_id=me["id"],
            notice_type=NotificationType.COMMENT_ON_CREATED,
            actor_name="Ada",
            issue_id=issue.id,
            issue_key=key,
            issue_title="Opened",
            body="Read me",
            created_at=datetime(2026, 11, 8, tzinfo=UTC),
        )
        notification_service.add_notice(
            session,
            recipient_id=me["id"],
            notice_type=NotificationType.UPDATE_ON_CREATED,
            actor_name="Ada",
            issue_id=issue.id,
            issue_key=key,
            issue_title="Still unread",
            body="Leave me",
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
        session.commit()
        opened_id = opened.id

    response = client.post(
        f"/web/notifications/{opened_id}/open",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/issues/{key}"
    landed = client.get(response.headers["location"])
    assert landed.status_code == 200
    assert "Hull" in landed.text
    assert "hidden" not in _dot(landed.text)

    page = client.get("/notifications")
    assert "Opened" in page.text
    assert "Still unread" in page.text
    assert "keel-notice--unread" not in page.text
    assert "hidden" in _dot(page.text)
    assert "hidden" in _dot(client.get("/").text)

    missing = client.post("/web/notifications/999999/open")
    assert "That notification does not exist." in missing.text


def test_a_deleted_issue_stays_readable_without_a_link(
    client: TestClient,
    app: FastAPI,
) -> None:
    me = client.get("/api/v1/profile").json()
    with app.state.session_factory() as session:
        notice = notification_service.add_notice(
            session,
            recipient_id=me["id"],
            notice_type=NotificationType.DELETE_ON_CREATED,
            actor_name="Ada",
            issue_key="KEEL-9",
            issue_title="Gone",
            body="This issue was deleted.",
        )
        session.commit()
        notice_id = notice.id

    page = client.get("/notifications")
    assert "KEEL-9 Gone" in page.text
    assert "This issue was deleted." in page.text
    assert 'href="/issues/KEEL-9"' not in page.text

    opened = client.post(f"/web/notifications/{notice_id}/open")
    assert opened.url.path == "/notifications"
    assert "KEEL-9 Gone" in opened.text
    assert "keel-notice--unread" not in opened.text
    assert 'href="/issues/KEEL-9"' not in opened.text


def test_the_person_can_delete_a_notice(client: TestClient, app: FastAPI) -> None:
    me = client.get("/api/v1/profile").json()
    with app.state.session_factory() as session:
        notice = notification_service.add_notice(
            session,
            recipient_id=me["id"],
            notice_type=NotificationType.COMMENT_ON_CREATED,
            actor_name="Ada",
            issue_key="KEEL-1",
            issue_title="Hull",
            body="A note",
        )
        session.commit()
        notice_id = notice.id

    removed = client.post(f"/web/notifications/{notice_id}/delete")
    assert removed.url.path == "/notifications"
    assert "There are no notifications." in removed.text
    assert "A note" not in removed.text
    assert "hidden" in _dot(removed.text)


def test_the_profile_grid_saves_any_combination_of_channels(
    client: TestClient,
) -> None:
    page = client.get("/profile")
    assert "Comment on an issue you created" in page.text
    assert "Someone assigns an issue to you" in page.text
    assert "Phone alert is saved here." in page.text
    assert _checked(page.text, "bell", "assigned")
    assert not _checked(page.text, "email", "assigned")
    assert not _checked(page.text, "phone", "assigned")

    types = [item.value for item in NotificationType]
    saved = client.post(
        "/web/profile/notifications",
        data={
            "notice_type": types,
            "email": [NotificationType.ASSIGNED.value],
            "phone": [NotificationType.COMMENT_ON_CREATED.value],
            "bell": [item for item in types if item != NotificationType.ASSIGNED.value],
        },
    )
    assert "Notification preferences saved." in saved.text
    assert _checked(saved.text, "email", "assigned")
    assert _checked(saved.text, "phone", "comment_on_created")
    assert not _checked(saved.text, "bell", "assigned")
    assert _checked(saved.text, "bell", "comment_on_created")

    prefs = client.get("/api/v1/notifications/preferences").json()
    assigned = next(item for item in prefs if item["type"] == "assigned")
    assert assigned == {
        "type": "assigned",
        "email": True,
        "phone": False,
        "bell": False,
    }

    refused = client.post(
        "/web/profile/notifications",
        data={"notice_type": [NotificationType.ASSIGNED.value]},
    )
    assert "Choose every notification type." in refused.text
    kept = client.get("/api/v1/notifications/preferences").json()
    assert next(item for item in kept if item["type"] == "assigned") == assigned


def test_another_persons_field_edit_notifies_the_reporter(
    client: TestClient,
    app: FastAPI,
) -> None:
    me = client.get("/api/v1/profile").json()
    with app.state.session_factory() as session:
        ada = user_service.create_user(session, "Ada")
        user_service.set_password(session, ada, "tester-password")
        project = project_service.create_project(session, "KEEL", "Keel")
        issue = issue_service.create_issue(
            session,
            project.id,
            type=IssueType.STORY,
            title="Hull",
            reporter_id=me["id"],
            assignee_id=me["id"],
        )
        issue_id = issue.id
        session.commit()

    with TestClient(app) as ada_client:
        signed = ada_client.post(
            "/login",
            data={"username": "Ada", "password": "tester-password"},
            follow_redirects=False,
        )
        assert signed.status_code == 303
        priority = ada_client.post(
            f"/web/issues/{issue_id}/priority",
            data={"priority": "p1"},
            follow_redirects=False,
        )
        assert priority.status_code == 303
        description = ada_client.post(
            f"/web/issues/{issue_id}/description",
            data={"description": "Plating"},
            follow_redirects=False,
        )
        assert description.status_code == 303
        status = ada_client.patch(
            f"/api/v1/issues/{issue_id}",
            json={"status": "in_progress"},
        )
        assert status.status_code == 200

    notices = client.get("/api/v1/notifications").json()
    assert len(notices) == 1
    notice = notices[0]
    assert notice["actor_name"] == "Ada"
    assert "priority:" in notice["body"]
    assert "description:" in notice["body"]
    assert "status:" in notice["body"]
    page = client.get("/notifications")
    assert "Plating" in page.text
    assert "hidden" in _dot(page.text)
