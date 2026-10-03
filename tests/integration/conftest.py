from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

TEST_PASSWORD = "tester-password"


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A signed-in client. The lifespan seeds Tester; this fixture sets a password."""
    with TestClient(app) as client:
        _grant_password(app, "Tester", TEST_PASSWORD)
        signed_in = client.post(
            "/login",
            data={"username": "Tester", "password": TEST_PASSWORD},
            follow_redirects=False,
        )
        assert signed_in.status_code == 303, signed_in.text
        yield client


@pytest.fixture
def anonymous_client(app: FastAPI) -> Iterator[TestClient]:
    """The seeded user has a password, and the client has not signed in."""
    with TestClient(app) as client:
        _grant_password(app, "Tester", TEST_PASSWORD)
        yield client


def _grant_password(app: FastAPI, username: str, password: str) -> None:
    from keel.services import users as user_service

    with app.state.session_factory() as session:
        user = user_service.find_by_username(session, username)
        assert user is not None
        user_service.set_password(session, user, password)
        session.commit()
