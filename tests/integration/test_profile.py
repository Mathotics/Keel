from fastapi.testclient import TestClient


def test_profile_contact_fields_round_trip(client: TestClient) -> None:
    me = client.get("/api/v1/profile").json()
    assert me["email"] == ""
    assert me["first_name"] == ""
    assert me["last_name"] == ""
    assert me["date_of_birth"] is None
    listed = client.get("/api/v1/users").json()
    assert "email" not in listed[0]
    assert "date_of_birth" not in listed[0]

    saved = client.patch(
        "/api/v1/profile",
        json={
            "display_name": me["display_name"],
            "username": me["username"],
            "email": " Ada@Example.com ",
            "first_name": " Ada ",
            "last_name": "Lovelace",
            "date_of_birth": "1815-12-10",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["email"] == "Ada@Example.com"
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["date_of_birth"] == "1815-12-10"

    kept = client.patch(
        "/api/v1/profile",
        json={"display_name": "Tess", "username": me["username"]},
    )
    assert kept.status_code == 200
    assert kept.json()["display_name"] == "Tess"
    assert kept.json()["email"] == "Ada@Example.com"
    assert kept.json()["date_of_birth"] == "1815-12-10"

    cleared = client.patch(
        "/api/v1/profile",
        json={
            "display_name": "Tess",
            "username": me["username"],
            "email": None,
            "first_name": "",
            "last_name": None,
            "date_of_birth": None,
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["email"] == ""
    assert cleared.json()["first_name"] == ""
    assert cleared.json()["last_name"] == ""
    assert cleared.json()["date_of_birth"] is None


def test_profile_rejects_an_unusable_email_and_a_future_birth_date(
    client: TestClient,
) -> None:
    me = client.get("/api/v1/profile").json()
    refused = client.patch(
        "/api/v1/profile",
        json={
            "display_name": me["display_name"],
            "username": me["username"],
            "email": "not-an-email",
        },
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "user.invalid_email"

    future = client.patch(
        "/api/v1/profile",
        json={
            "display_name": me["display_name"],
            "username": me["username"],
            "date_of_birth": "2999-01-01",
        },
    )
    assert future.status_code == 422
    assert future.json()["detail"]["code"] == "user.invalid_date_of_birth"
    assert client.get("/api/v1/profile").json()["email"] == ""


def test_profile_page_saves_optional_fields(client: TestClient) -> None:
    page = client.get("/profile")
    assert page.status_code == 200
    assert 'name="email"' in page.text
    assert 'name="date_of_birth"' in page.text

    saved = client.post(
        "/web/profile",
        data={
            "display_name": "Tester",
            "username": "Tester",
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
            "date_of_birth": "1906-12-09",
        },
    )
    assert "Profile updated." in saved.text
    assert 'value="Grace"' in saved.text
    assert 'value="Hopper"' in saved.text
    assert 'value="grace@example.com"' in saved.text
    assert 'value="1906-12-09"' in saved.text

    refused = client.post(
        "/web/profile",
        data={
            "display_name": "Tester",
            "username": "Tester",
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "nope",
            "date_of_birth": "1906-12-09",
        },
    )
    assert "name@example.com" in refused.text
    still = client.get("/api/v1/profile").json()
    assert still["email"] == "grace@example.com"
    assert still["date_of_birth"] == "1906-12-09"

    cleared = client.post(
        "/web/profile",
        data={
            "display_name": "Tester",
            "username": "Tester",
            "first_name": "",
            "last_name": "",
            "email": "",
            "date_of_birth": "",
        },
    )
    assert "Profile updated." in cleared.text
    blank = client.get("/api/v1/profile").json()
    assert blank["email"] == ""
    assert blank["first_name"] == ""
    assert blank["last_name"] == ""
    assert blank["date_of_birth"] is None
