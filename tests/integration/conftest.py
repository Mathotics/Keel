from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Enters the lifespan, so the default user is seeded as it is in production."""
    with TestClient(app) as client:
        yield client
