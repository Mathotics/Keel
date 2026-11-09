from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.domain.enums import NotificationType
from keel.services import notifications as notification_service
from keel.services import users as user_service


def _grid(
    email_for: NotificationType | None = None,
) -> dict[str, list[dict[str, str | bool]]]:
    return {
        "preferences": [
            {
                "type": item.value,
                "email": item is email_for,
                "phone": False,
                "bell": True,
            }
            for item in NotificationType
        ],
    }


def test_preferences_round_trip_and_default_to_the_bell(client: TestClient) -> None:
    defaults = client.get("/api/v1/notifications/preferences")
    assert defaults.status_code == 200
    assert len(defaults.json()) == len(NotificationType)
    assert all(
        item["bell"] and not item["email"] and not item["phone"]
        for item in defaults.json()
    )

    replaced = client.put(
        "/api/v1/notifications/preferences",
        json=_grid(NotificationType.ASSIGNED),
    )
    assert replaced.status_code == 200
    assigned = next(item for item in replaced.json() if item["type"] == "assigned")
    assert assigned["email"] is True
    comment = next(
        item for item in replaced.json() if item["type"] == "comment_on_created"
    )
    assert comment["email"] is False

    refused = client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": _grid()["preferences"][:6]},
    )
    assert refused.status_code == 422


def test_the_inbox_is_private_to_the_signed_in_person(
    client: TestClient,
    app: FastAPI,
) -> None:
    profile = client.get("/api/v1/profile").json()
    with app.state.session_factory() as session:
        ada_id = user_service.create_user(session, "Ada").id
        mine = notification_service.add_notice(
            session,
            recipient_id=profile["id"],
            notice_type=NotificationType.COMMENT_ON_CREATED,
            actor_id=ada_id,
            actor_name="Ada",
            issue_key="KEEL-1",
            issue_title="Hull",
            body="A note",
        )
        theirs = notification_service.add_notice(
            session,
            recipient_id=ada_id,
            notice_type=NotificationType.ASSIGNED,
            actor_name="Tester",
            issue_key="KEEL-2",
            issue_title="Deck",
        )
        session.commit()
        mine_id = mine.id
        theirs_id = theirs.id

    listed = client.get("/api/v1/notifications")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [mine_id]
    assert listed.json()[0]["issue_key"] == "KEEL-1"
    assert listed.json()[0]["read_at"] is None

    hidden = client.post(f"/api/v1/notifications/{theirs_id}/read")
    assert hidden.status_code == 404
    removed = client.delete(f"/api/v1/notifications/{theirs_id}")
    assert removed.status_code == 404

    opened = client.post(f"/api/v1/notifications/{mine_id}/read")
    assert opened.status_code == 200
    assert opened.json()["read_at"] is not None
    again = client.post(f"/api/v1/notifications/{mine_id}/read")
    assert again.json()["read_at"] == opened.json()["read_at"]

    deleted = client.delete(f"/api/v1/notifications/{mine_id}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/notifications").json() == []

    with app.state.session_factory() as session:
        assert notification_service.list_notices(session, ada_id)[0].id == theirs_id


def test_anonymous_notification_routes_require_sign_in(
    anonymous_client: TestClient,
) -> None:
    assert anonymous_client.get("/api/v1/notifications").status_code == 401
    assert anonymous_client.get("/api/v1/notifications/preferences").status_code == 401
