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


def test_permission_choices_name_the_required_code() -> None:
    from keel.services.access import permission_choices

    by_code = {code: required for code, _label, _text, required in permission_choices()}
    assert by_code["view_log_tracker"] == "display_admin_menu"
    assert by_code["manage_global_rbac"] == "view_global_rbac"
    assert by_code["view_projects"] == ""
    assert by_code["may_create_issues"] == "view_projects"
    assert by_code["may_delete_sprints"] == "view_projects"


def test_the_catalog_names_role_bundles_and_dependencies() -> None:
    from keel.services.access import access_catalog

    roles, permissions = access_catalog()
    by_role = {row.label: row.permissions for row in roles}
    assert "View users" in by_role["Admin"]
    assert by_role["Member"] == (
        "View projects, Create issues, Edit issues, Create comments, "
        "Create schedules, Edit schedules"
    )
    assert "Delete issues" not in by_role["Member"]
    assert "Delete comments" not in by_role["Member"]
    assert "Create sprints" not in by_role["Member"]
    assert by_role["Owner"] == "Bypasses every global and project permission"
    assert by_role["Custom"] == "None"
    assert "Delete own comments" in by_role["Contributor"]
    assert "Delete any comment" not in by_role["Contributor"]
    assert "Delete any comment" in by_role["Project Owner"]
    by_permission = {row.label: row.requires for row in permissions}
    assert by_permission["Create projects"] == "View projects"
    assert by_permission["Create issues"] == "View projects"
    assert by_permission["Create issues in a project"] == "View issues"
    assert by_permission["Manage global RBAC"] == "View global RBAC page"
    assert by_permission["View projects"] == "None"
    assert by_permission["Delete any comment"] == "Delete own comments"


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


def test_member_can_see_projects_and_create_and_edit_issues_and_schedules() -> None:
    is_owner, held = effective_global(frozenset({RoleCode.MEMBER}), frozenset())
    assert is_owner is False
    assert held == frozenset(
        {
            Permission.VIEW_PROJECTS,
            Permission.MAY_CREATE_ISSUES,
            Permission.MAY_EDIT_ISSUES,
            Permission.MAY_CREATE_COMMENTS,
            Permission.MAY_CREATE_SCHEDULES,
            Permission.MAY_EDIT_SCHEDULES,
        }
    )
    assert Permission.MAY_DELETE_ISSUES not in held
    assert Permission.MAY_DELETE_COMMENTS not in held
    assert Permission.MAY_CREATE_SPRINTS not in held


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
    assert Permission.COMMENT_ISSUES in held
    assert Permission.DELETE_OWN_COMMENTS not in held
    assert Permission.DELETE_ISSUES not in held
    assert Permission.DELETE_ANY_COMMENTS not in held
    assert Permission.CREATE_SPRINTS not in held


def test_a_project_write_also_needs_its_global_permission() -> None:
    _bypass, held = effective_project(
        frozenset({RoleCode.MEMBER}),
        frozenset({RoleCode.PROJECT_OWNER}),
        frozenset(),
    )
    assert Permission.CREATE_ISSUES in held
    assert Permission.EDIT_SCHEDULES in held
    assert Permission.VIEW_ISSUES in held
    assert Permission.COMMENT_ISSUES in held
    assert Permission.DELETE_OWN_COMMENTS not in held
    assert Permission.DELETE_ANY_COMMENTS not in held
    assert Permission.DELETE_ISSUES not in held
    assert Permission.CREATE_SPRINTS not in held
    assert Permission.UPDATE_ISSUES in held
    with_delete = effective_project(
        frozenset({RoleCode.MEMBER}),
        frozenset({RoleCode.PROJECT_OWNER}),
        frozenset({Permission.MAY_DELETE_ISSUES}),
    )[1]
    assert Permission.DELETE_ISSUES in with_delete
    with_comment_delete = effective_project(
        frozenset({RoleCode.MEMBER}),
        frozenset({RoleCode.PROJECT_OWNER}),
        frozenset({Permission.MAY_DELETE_COMMENTS}),
    )[1]
    assert Permission.DELETE_OWN_COMMENTS in with_comment_delete
    assert Permission.DELETE_ANY_COMMENTS in with_comment_delete
    as_admin = effective_project(
        frozenset({RoleCode.ADMIN}),
        frozenset({RoleCode.PROJECT_OWNER}),
        frozenset(),
    )[1]
    assert Permission.DELETE_ISSUES in as_admin
    assert Permission.DELETE_SPRINTS in as_admin


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
            requested_custom=False,
            actor_is_owner=False,
            target_is_owner=False,
            other_owners=1,
        )


def test_the_last_owner_cannot_be_removed() -> None:
    with pytest.raises(LastOwnerError):
        resolve_global_roles(
            requested_owner=False,
            requested_admin=True,
            requested_custom=False,
            actor_is_owner=True,
            target_is_owner=True,
            other_owners=0,
        )


def test_clearing_owner_and_admin_stores_member() -> None:
    roles = resolve_global_roles(
        requested_owner=False,
        requested_admin=False,
        requested_custom=False,
        actor_is_owner=True,
        target_is_owner=False,
        other_owners=1,
    )
    assert roles == frozenset({RoleCode.MEMBER})


def test_owner_and_admin_can_be_held_together() -> None:
    roles = resolve_global_roles(
        requested_owner=True,
        requested_admin=True,
        requested_custom=False,
        actor_is_owner=True,
        target_is_owner=True,
        other_owners=0,
    )
    assert roles == frozenset({RoleCode.OWNER, RoleCode.ADMIN})


def test_custom_holds_only_the_grants_for_that_person() -> None:
    assert ROLE_PERMISSIONS[RoleCode.CUSTOM] == frozenset()
    roles = resolve_global_roles(
        requested_owner=False,
        requested_admin=False,
        requested_custom=True,
        actor_is_owner=True,
        target_is_owner=False,
        other_owners=1,
    )
    assert roles == frozenset({RoleCode.CUSTOM})
    replaced = resolve_global_roles(
        requested_owner=True,
        requested_admin=False,
        requested_custom=True,
        actor_is_owner=True,
        target_is_owner=False,
        other_owners=1,
    )
    assert replaced == frozenset({RoleCode.OWNER})
    is_owner, held = effective_global(
        frozenset({RoleCode.CUSTOM}),
        frozenset({Permission.VIEW_PROJECTS, Permission.MAY_CREATE_ISSUES}),
    )
    assert is_owner is False
    assert held == frozenset({Permission.VIEW_PROJECTS, Permission.MAY_CREATE_ISSUES})
    project = effective_project(
        frozenset({RoleCode.CUSTOM}),
        frozenset({RoleCode.PROJECT_OWNER}),
        frozenset({Permission.VIEW_PROJECTS, Permission.MAY_CREATE_ISSUES}),
    )[1]
    assert Permission.CREATE_ISSUES in project
    assert Permission.EDIT_ISSUES not in project
    assert Permission.VIEW_ISSUES in project
