"""Project resolvers and the permission guard routes will share."""

from datetime import date

import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from keel.api.v1.guards import (
    current_access,
    guard_issue,
    permissions_for_issue_update,
)
from keel.db.models import Series
from keel.domain.access import Permission, RoleCode
from keel.domain.enums import (
    DependencyKind,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
)
from keel.domain.errors import NotFoundError, PermissionDeniedError
from keel.services import access as access_service
from keel.services import comments as comment_service
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.access import Access
from keel.web.context import Chrome
from keel.web.forbid import require_project_page


def _person(session: Session, name: str, role: RoleCode) -> Access:
    user = user_service.create_user(session, name, name, "person-password-1")
    access_service.replace_global_roles(session, user.id, frozenset({role}))
    return access_service.load_access(session, user.id)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/projects/KEEL",
            "raw_path": b"/projects/KEEL",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
            "root_path": "",
        }
    )


def test_owner_bypasses_a_project_the_owner_has_no_role_on(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    owner = _person(session, "Owner", RoleCode.OWNER)

    access_service.require_project(session, owner, project.id, Permission.DELETE_ISSUES)


def test_no_access_is_denied_even_with_a_stored_project_role(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    blocked = _person(session, "Mallory", RoleCode.MEMBER)
    assert blocked.user_id is not None
    access_service.set_project_role(
        session, blocked.user_id, project.id, RoleCode.PROJECT_OWNER
    )
    access_service.replace_global_roles(
        session, blocked.user_id, frozenset({RoleCode.NO_ACCESS})
    )
    blocked = access_service.load_access(session, blocked.user_id)

    with pytest.raises(PermissionDeniedError):
        access_service.require_project(
            session, blocked, project.id, Permission.VIEW_ISSUES
        )


def test_a_viewer_may_read_and_may_not_write(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    viewer = _person(session, "Viewer", RoleCode.MEMBER)
    assert viewer.user_id is not None
    access_service.set_project_role(
        session, viewer.user_id, project.id, RoleCode.VIEWER
    )

    access_service.require_project(session, viewer, project.id, Permission.VIEW_ISSUES)
    with pytest.raises(PermissionDeniedError):
        access_service.require_project(
            session, viewer, project.id, Permission.CREATE_ISSUES
        )


def test_the_global_gate_blocks_a_project_write(session: Session) -> None:
    """Contributor includes create, but Custom holds no global create permission."""
    project = project_service.create_project(session, "KEEL", "Keel")
    custom = _person(session, "Custom", RoleCode.CUSTOM)
    assert custom.user_id is not None
    access_service.set_project_role(
        session, custom.user_id, project.id, RoleCode.CONTRIBUTOR
    )

    access_service.require_project(session, custom, project.id, Permission.VIEW_ISSUES)
    with pytest.raises(PermissionDeniedError):
        access_service.require_project(
            session, custom, project.id, Permission.CREATE_ISSUES
        )


def test_a_role_change_is_visible_on_the_next_check(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    member = _person(session, "Member", RoleCode.MEMBER)
    assert member.user_id is not None
    assert not access_service.holds_project(
        session, member, project.id, Permission.VIEW_ISSUES
    )

    access_service.set_project_role(
        session, member.user_id, project.id, RoleCode.VIEWER
    )

    assert access_service.holds_project(
        session, member, project.id, Permission.VIEW_ISSUES
    )


def test_resolvers_follow_an_issue_to_its_project(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    other = project_service.create_project(session, "BOAT", "Boat")
    issue = issue_service.create_issue(
        session, project.id, type=IssueType.STORY, title="Hull"
    )
    other_issue = issue_service.create_issue(
        session, other.id, type=IssueType.STORY, title="Sail"
    )
    sprint = sprint_service.create_sprint(session, project.id, name="This week")
    comment = comment_service.create_comment(session, issue.id, "Noted")
    link = dependency_service.create_dependency(
        session, issue.id, other_issue.id, DependencyKind.RELATES_TO
    )
    series = Series(
        project_id=project.id,
        title="Weekly",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.CALENDAR,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.WEEKLY,
        starts_on=date(2026, 11, 14),
    )
    session.add(series)
    session.flush()

    assert access_service.project_of_issue(session, issue.id) == project.id
    assert access_service.project_of_issue_key(session, "KEEL-1") == project.id
    assert access_service.project_of_sprint(session, sprint.id) == project.id
    assert access_service.project_of_series(session, series.id) == project.id
    assert access_service.project_of_comment(session, comment.id) == project.id
    ends = access_service.project_of_dependency(session, link.id)
    assert ends.source_project_id == project.id
    assert ends.target_project_id == other.id
    with pytest.raises(NotFoundError):
        access_service.project_of_issue(session, 0)


def test_anonymous_callers_are_refused(session: Session) -> None:
    with pytest.raises(PermissionDeniedError):
        current_access(session, None)


def test_guard_issue_denies_a_viewer_write(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    issue = issue_service.create_issue(
        session, project.id, type=IssueType.STORY, title="Hull"
    )
    viewer = _person(session, "Viewer", RoleCode.MEMBER)
    assert viewer.user_id is not None
    access_service.set_project_role(
        session, viewer.user_id, project.id, RoleCode.VIEWER
    )

    assert guard_issue(session, viewer, issue.id, Permission.VIEW_ISSUES) == project.id
    with pytest.raises(PermissionDeniedError):
        guard_issue(session, viewer, issue.id, Permission.EDIT_ISSUES)


def test_the_web_guard_renders_the_forbidden_page(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    viewer = _person(session, "Viewer", RoleCode.MEMBER)
    blocked = _person(session, "Mallory", RoleCode.NO_ACCESS)
    assert viewer.user_id is not None
    access_service.set_project_role(
        session, viewer.user_id, project.id, RoleCode.VIEWER
    )
    viewer_user = user_service.get_user(session, viewer.user_id)
    blocked_user = user_service.get_user(session, blocked.user_id or 0)
    request = _request()

    allowed = require_project_page(
        request,
        Chrome(
            users=(viewer_user,),
            current_user=viewer_user,
            access=viewer,
            unread=False,
        ),
        session,
        project.id,
        Permission.VIEW_ISSUES,
    )
    denied = require_project_page(
        request,
        Chrome(
            users=(blocked_user,),
            current_user=blocked_user,
            access=blocked,
            unread=False,
        ),
        session,
        project.id,
        Permission.VIEW_ISSUES,
    )

    assert allowed is None
    assert denied is not None
    assert denied.status_code == 403


def test_issue_update_permissions_split_status_from_edits() -> None:
    assert permissions_for_issue_update(set()) == (Permission.EDIT_ISSUES,)
    assert permissions_for_issue_update({"status"}) == (Permission.UPDATE_ISSUES,)
    assert permissions_for_issue_update({"title"}) == (Permission.EDIT_ISSUES,)
    assert permissions_for_issue_update({"status", "title"}) == (
        Permission.UPDATE_ISSUES,
        Permission.EDIT_ISSUES,
    )
