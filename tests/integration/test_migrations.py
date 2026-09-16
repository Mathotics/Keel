from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from keel import cli
from keel.app import create_app
from keel.db.engine import create_db_engine
from keel.settings import KeelSettings


@pytest.fixture
def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KeelSettings:
    url = f"sqlite+pysqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    settings = KeelSettings(_env_file=None, database_url=url, default_user="Owner")
    monkeypatch.setattr("keel.cli.get_settings", lambda: settings)
    cli.main(["db", "upgrade"])
    return settings


def test_the_app_runs_on_a_migrated_database(migrated: KeelSettings) -> None:
    """The path a real install takes: keel db upgrade, then keel serve."""
    with TestClient(create_app(migrated)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        assert [u["display_name"] for u in client.get("/api/v1/users").json()] == [
            "Owner"
        ]


def test_migrations_and_models_agree(migrated: KeelSettings) -> None:
    """A column added to a model without a migration would show up here."""
    engine = create_db_engine(migrated.resolved_database_url())
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("users")}
    finally:
        engine.dispose()
    assert columns == {"id", "display_name", "created_at"}


def test_issue_migrations_include_due_at(migrated: KeelSettings) -> None:
    engine = create_db_engine(migrated.resolved_database_url())
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("issues")}
        sprints = {column["name"] for column in inspect(engine).get_columns("sprints")}
        dependencies = {
            column["name"] for column in inspect(engine).get_columns("dependencies")
        }
        comments = {
            column["name"] for column in inspect(engine).get_columns("comments")
        }
        projects = {
            column["name"] for column in inspect(engine).get_columns("projects")
        }
        series = {column["name"] for column in inspect(engine).get_columns("series")}
        labels = {column["name"] for column in inspect(engine).get_columns("labels")}
        issue_labels = {
            column["name"] for column in inspect(engine).get_columns("issue_labels")
        }
    finally:
        engine.dispose()
    assert "due_at" in columns
    assert "series_id" in columns
    assert "occurrence_on" in columns
    assert "sprint_id" in columns
    assert "created_at" in columns
    assert "updated_at" in columns
    assert sprints >= {
        "id",
        "project_id",
        "name",
        "goal",
        "state",
        "starts_on",
        "ends_on",
        "created_at",
        "completed_at",
    }
    assert dependencies == {
        "id",
        "source_id",
        "target_id",
        "kind",
        "created_at",
    }
    assert comments == {
        "id",
        "issue_id",
        "author_id",
        "body",
        "created_at",
    }
    assert labels == {"id", "name", "created_at"}
    assert issue_labels == {"issue_id", "label_id"}
    labels = {column["name"] for column in inspect(engine).get_columns("labels")}
    issue_labels = {
        column["name"] for column in inspect(engine).get_columns("issue_labels")
    }
    assert projects >= {
        "sprint_cadence",
        "sprint_cadence_days",
        "auto_sprint_notice",
    }
    assert series >= {
        "id",
        "project_id",
        "title",
        "spawn_mode",
        "look_ahead_n",
        "freq",
        "starts_on",
    }


def test_seeding_is_idempotent_across_restarts(migrated: KeelSettings) -> None:
    for _ in range(2):
        with TestClient(create_app(migrated)) as client:
            users = client.get("/api/v1/users").json()
    assert len(users) == 1
