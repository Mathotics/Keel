import pytest

from keel.domain.access import (
    GLOBAL_PERMISSIONS,
    PROJECT_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    RoleCode,
    apply_direct_grants,
    close,
    effective_global,
    effective_project,
    resolve_global_roles,
)
from keel.domain.errors import LastOwnerError, OwnerChangeDeniedError


def test_checking_a_permission_adds_what_it_requires() -> None:
    saved = apply_direct_grants(
        frozenset(),
        frozenset({Permission.CREATE_USERS}),
    )
    assert saved == frozenset({Permission.CREATE_USERS, Permission.VIEW_USERS})


def test_unchecking_a_dependency_drops_what_needed_it() -> None:
    previous = close(
        frozenset({Permission.CREATE_USERS, Permission.DELETE_USERS}),
    )
    saved = apply_direct_grants(previous, frozenset({Permission.CREATE_USERS}))
    assert saved == frozenset()


def test_unchecking_view_users_drops_the_user_actions() -> None:
    previous = close(frozenset({Permission.CREATE_USERS, Permission.DELETE_USERS}))
    saved = apply_direct_grants(previous, frozenset())
    assert saved == frozenset()


def test_delete_any_comment_includes_delete_own() -> None:
    saved = close(frozenset({Permission.DELETE_ANY_COMMENTS}))
    assert Permission.DELETE_OWN_COMMENTS in saved
    assert Permission.COMMENT_ISSUES in saved


def test_member_has_no_global_permissions() -> None:
    is_owner, held = effective_global(frozenset({RoleCode.MEMBER}), frozenset())
    assert is_owner is False
    assert held == frozenset()


def test_admin_holds_every_global_permission_and_no_project_bypass() -> None:
    is_owner, held = effective_global(frozenset({RoleCode.ADMIN}), frozenset())
    assert is_owner is False
    assert held == frozenset(GLOBAL_PERMISSIONS)
    bypass, project = effective_project(
        frozenset({RoleCode.ADMIN}),
        frozenset(),
        frozenset(),
    )
    assert bypass is False
    assert project == frozenset()


def test_owner_bypasses_global_and_project_checks() -> None:
    is_owner, held = effective_global(frozenset({RoleCode.OWNER}), frozenset())
    assert is_owner is True
    assert held == frozenset(GLOBAL_PERMISSIONS)
    bypass, project = effective_project(
        frozenset({RoleCode.OWNER}),
        frozenset(),
        frozenset(),
    )
    assert bypass is True
    assert project == frozenset(PROJECT_PERMISSIONS)


def test_contributor_cannot_delete_issues_or_other_peoples_comments() -> None:
    _bypass, held = effective_project(
        frozenset({RoleCode.MEMBER}),
        frozenset({RoleCode.CONTRIBUTOR}),
        frozenset(),
    )
    assert Permission.CREATE_ISSUES in held
    assert Permission.DELETE_OWN_COMMENTS in held
    assert Permission.DELETE_ISSUES not in held
    assert Permission.DELETE_ANY_COMMENTS not in held
    assert Permission.CREATE_SPRINTS not in held


def test_project_owner_includes_the_contributor_bundle() -> None:
    owner = ROLE_PERMISSIONS[RoleCode.PROJECT_OWNER]
    contributor = ROLE_PERMISSIONS[RoleCode.CONTRIBUTOR]
    assert contributor <= owner
    assert Permission.DELETE_ANY_COMMENTS in owner


def test_a_direct_grant_without_its_dependency_does_not_count() -> None:
    _owner, held = effective_global(
        frozenset({RoleCode.MEMBER}),
        frozenset({Permission.CREATE_USERS}),
    )
    assert Permission.CREATE_USERS not in held


def test_only_an_owner_can_change_owner_membership() -> None:
    with pytest.raises(OwnerChangeDeniedError):
        resolve_global_roles(
            requested_owner=True,
            requested_admin=False,
            actor_is_owner=False,
            target_is_owner=False,
            other_owners=1,
        )


def test_the_last_owner_cannot_be_removed() -> None:
    with pytest.raises(LastOwnerError):
        resolve_global_roles(
            requested_owner=False,
            requested_admin=True,
            actor_is_owner=True,
            target_is_owner=True,
            other_owners=0,
        )


def test_clearing_owner_and_admin_stores_member() -> None:
    roles = resolve_global_roles(
        requested_owner=False,
        requested_admin=False,
        actor_is_owner=True,
        target_is_owner=False,
        other_owners=1,
    )
    assert roles == frozenset({RoleCode.MEMBER})


def test_owner_and_admin_can_be_held_together() -> None:
    roles = resolve_global_roles(
        requested_owner=True,
        requested_admin=True,
        actor_is_owner=True,
        target_is_owner=True,
        other_owners=0,
    )
    assert roles == frozenset({RoleCode.OWNER, RoleCode.ADMIN})
