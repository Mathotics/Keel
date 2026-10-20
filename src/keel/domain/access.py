"""Roles, permissions, and the rules that connect them.

Pure data. Nothing here touches the database. Project checks are part of the
catalog so a later story can enforce them without inventing a second list.
"""

from enum import StrEnum

from keel.domain.errors import LastOwnerError, OwnerChangeDeniedError


class Scope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"


class RoleCode(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    CUSTOM = "custom"
    PROJECT_OWNER = "project_owner"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


class Permission(StrEnum):
    VIEW_PROJECTS = "view_projects"
    CREATE_PROJECTS = "create_projects"
    DELETE_PROJECTS = "delete_projects"
    MAY_CREATE_ISSUES = "may_create_issues"
    MAY_EDIT_ISSUES = "may_edit_issues"
    MAY_DELETE_ISSUES = "may_delete_issues"
    MAY_CREATE_COMMENTS = "may_create_comments"
    MAY_DELETE_COMMENTS = "may_delete_comments"
    MAY_CREATE_SCHEDULES = "may_create_schedules"
    MAY_EDIT_SCHEDULES = "may_edit_schedules"
    MAY_DELETE_SCHEDULES = "may_delete_schedules"
    MAY_CREATE_SPRINTS = "may_create_sprints"
    MAY_EDIT_SPRINTS = "may_edit_sprints"
    MAY_DELETE_SPRINTS = "may_delete_sprints"
    DISPLAY_ADMIN_MENU = "display_admin_menu"
    VIEW_LOG_TRACKER = "view_log_tracker"
    VIEW_GLOBAL_RBAC = "view_global_rbac"
    MANAGE_GLOBAL_RBAC = "manage_global_rbac"
    VIEW_USERS = "view_users"
    CREATE_USERS = "create_users"
    DELETE_USERS = "delete_users"
    RENAME_USERS = "rename_users"
    RESET_USER_PASSWORDS = "reset_user_passwords"
    VIEW_ISSUES = "view_issues"
    VIEW_BACKLOG = "view_backlog"
    VIEW_BOARD = "view_board"
    VIEW_CALENDAR = "view_calendar"
    VIEW_SPRINTS = "view_sprints"
    VIEW_SCHEDULES = "view_schedules"
    CREATE_ISSUES = "create_issues"
    EDIT_ISSUES = "edit_issues"
    UPDATE_ISSUES = "update_issues"
    DELETE_ISSUES = "delete_issues"
    COMMENT_ISSUES = "comment_issues"
    DELETE_OWN_COMMENTS = "delete_own_comments"
    DELETE_ANY_COMMENTS = "delete_any_comments"
    MANAGE_DEPENDENCIES = "manage_dependencies"
    CREATE_SPRINTS = "create_sprints"
    EDIT_SPRINTS = "edit_sprints"
    DELETE_SPRINTS = "delete_sprints"
    START_COMPLETE_SPRINTS = "start_complete_sprints"
    CREATE_SCHEDULES = "create_schedules"
    EDIT_SCHEDULES = "edit_schedules"
    DELETE_SCHEDULES = "delete_schedules"
    CHANGE_PROJECT_SETTINGS = "change_project_settings"
    DELETE_PROJECT = "delete_project"
    VIEW_PROJECT_RBAC = "view_project_rbac"
    MANAGE_PROJECT_RBAC = "manage_project_rbac"


# A permission maps to the permissions that must already be held.
DEPENDENCIES: dict[Permission, frozenset[Permission]] = {
    Permission.CREATE_PROJECTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.DELETE_PROJECTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_CREATE_ISSUES: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_EDIT_ISSUES: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_DELETE_ISSUES: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_CREATE_COMMENTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_DELETE_COMMENTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_CREATE_SCHEDULES: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_EDIT_SCHEDULES: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_DELETE_SCHEDULES: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_CREATE_SPRINTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_EDIT_SPRINTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.MAY_DELETE_SPRINTS: frozenset({Permission.VIEW_PROJECTS}),
    Permission.VIEW_LOG_TRACKER: frozenset({Permission.DISPLAY_ADMIN_MENU}),
    Permission.VIEW_GLOBAL_RBAC: frozenset({Permission.DISPLAY_ADMIN_MENU}),
    Permission.MANAGE_GLOBAL_RBAC: frozenset({Permission.VIEW_GLOBAL_RBAC}),
    Permission.CREATE_USERS: frozenset({Permission.VIEW_USERS}),
    Permission.DELETE_USERS: frozenset({Permission.VIEW_USERS}),
    Permission.RENAME_USERS: frozenset({Permission.VIEW_USERS}),
    Permission.RESET_USER_PASSWORDS: frozenset({Permission.VIEW_USERS}),
    Permission.VIEW_BACKLOG: frozenset({Permission.VIEW_ISSUES}),
    Permission.VIEW_BOARD: frozenset({Permission.VIEW_ISSUES}),
    Permission.VIEW_CALENDAR: frozenset({Permission.VIEW_ISSUES}),
    Permission.CREATE_ISSUES: frozenset({Permission.VIEW_ISSUES}),
    Permission.EDIT_ISSUES: frozenset({Permission.VIEW_ISSUES}),
    Permission.UPDATE_ISSUES: frozenset({Permission.VIEW_ISSUES}),
    Permission.DELETE_ISSUES: frozenset({Permission.VIEW_ISSUES}),
    Permission.COMMENT_ISSUES: frozenset({Permission.VIEW_ISSUES}),
    Permission.DELETE_OWN_COMMENTS: frozenset({Permission.COMMENT_ISSUES}),
    Permission.DELETE_ANY_COMMENTS: frozenset({Permission.DELETE_OWN_COMMENTS}),
    Permission.MANAGE_DEPENDENCIES: frozenset({Permission.VIEW_ISSUES}),
    Permission.CREATE_SPRINTS: frozenset({Permission.VIEW_SPRINTS}),
    Permission.EDIT_SPRINTS: frozenset({Permission.VIEW_SPRINTS}),
    Permission.DELETE_SPRINTS: frozenset({Permission.VIEW_SPRINTS}),
    Permission.START_COMPLETE_SPRINTS: frozenset({Permission.VIEW_SPRINTS}),
    Permission.CREATE_SCHEDULES: frozenset({Permission.VIEW_SCHEDULES}),
    Permission.EDIT_SCHEDULES: frozenset({Permission.VIEW_SCHEDULES}),
    Permission.DELETE_SCHEDULES: frozenset({Permission.VIEW_SCHEDULES}),
    Permission.CHANGE_PROJECT_SETTINGS: frozenset({Permission.VIEW_ISSUES}),
    Permission.DELETE_PROJECT: frozenset({Permission.VIEW_ISSUES}),
    Permission.VIEW_PROJECT_RBAC: frozenset({Permission.VIEW_ISSUES}),
    Permission.MANAGE_PROJECT_RBAC: frozenset({Permission.VIEW_PROJECT_RBAC}),
}

LABELS: dict[Permission, str] = {
    Permission.VIEW_PROJECTS: "View projects",
    Permission.CREATE_PROJECTS: "Create projects",
    Permission.DELETE_PROJECTS: "Delete projects",
    Permission.MAY_CREATE_ISSUES: "Create issues",
    Permission.MAY_EDIT_ISSUES: "Edit issues",
    Permission.MAY_DELETE_ISSUES: "Delete issues",
    Permission.MAY_CREATE_COMMENTS: "Create comments",
    Permission.MAY_DELETE_COMMENTS: "Delete comments",
    Permission.MAY_CREATE_SCHEDULES: "Create schedules",
    Permission.MAY_EDIT_SCHEDULES: "Edit schedules",
    Permission.MAY_DELETE_SCHEDULES: "Delete schedules",
    Permission.MAY_CREATE_SPRINTS: "Create sprints",
    Permission.MAY_EDIT_SPRINTS: "Edit sprints",
    Permission.MAY_DELETE_SPRINTS: "Delete sprints",
    Permission.DISPLAY_ADMIN_MENU: "Display Admin menu",
    Permission.VIEW_LOG_TRACKER: "View Log Tracker",
    Permission.VIEW_GLOBAL_RBAC: "View global RBAC page",
    Permission.MANAGE_GLOBAL_RBAC: "Manage global RBAC",
    Permission.VIEW_USERS: "View users",
    Permission.CREATE_USERS: "Create users",
    Permission.DELETE_USERS: "Delete users",
    Permission.RENAME_USERS: "Rename users",
    Permission.RESET_USER_PASSWORDS: "Reset another user's password",
    Permission.VIEW_ISSUES: "View issues",
    Permission.VIEW_BACKLOG: "View backlog",
    Permission.VIEW_BOARD: "View board",
    Permission.VIEW_CALENDAR: "View calendar",
    Permission.VIEW_SPRINTS: "View sprints",
    Permission.VIEW_SCHEDULES: "View schedules",
    Permission.CREATE_ISSUES: "Create issues in a project",
    Permission.EDIT_ISSUES: "Edit issues in a project",
    Permission.UPDATE_ISSUES: "Update issues",
    Permission.DELETE_ISSUES: "Delete issues in a project",
    Permission.COMMENT_ISSUES: "Comment on issues",
    Permission.DELETE_OWN_COMMENTS: "Delete own comments",
    Permission.DELETE_ANY_COMMENTS: "Delete any comment",
    Permission.MANAGE_DEPENDENCIES: "Manage dependencies",
    Permission.CREATE_SPRINTS: "Create sprints in a project",
    Permission.EDIT_SPRINTS: "Edit sprints in a project",
    Permission.DELETE_SPRINTS: "Delete sprints in a project",
    Permission.START_COMPLETE_SPRINTS: "Start or complete sprints",
    Permission.CREATE_SCHEDULES: "Create schedules in a project",
    Permission.EDIT_SCHEDULES: "Edit schedules in a project",
    Permission.DELETE_SCHEDULES: "Delete schedules in a project",
    Permission.CHANGE_PROJECT_SETTINGS: "Change project settings",
    Permission.DELETE_PROJECT: "Delete this project",
    Permission.VIEW_PROJECT_RBAC: "View project RBAC page",
    Permission.MANAGE_PROJECT_RBAC: "Manage project RBAC",
}

GLOBAL_PERMISSIONS: tuple[Permission, ...] = (
    Permission.VIEW_PROJECTS,
    Permission.CREATE_PROJECTS,
    Permission.DELETE_PROJECTS,
    Permission.MAY_CREATE_ISSUES,
    Permission.MAY_EDIT_ISSUES,
    Permission.MAY_DELETE_ISSUES,
    Permission.MAY_CREATE_COMMENTS,
    Permission.MAY_DELETE_COMMENTS,
    Permission.MAY_CREATE_SCHEDULES,
    Permission.MAY_EDIT_SCHEDULES,
    Permission.MAY_DELETE_SCHEDULES,
    Permission.MAY_CREATE_SPRINTS,
    Permission.MAY_EDIT_SPRINTS,
    Permission.MAY_DELETE_SPRINTS,
    Permission.DISPLAY_ADMIN_MENU,
    Permission.VIEW_LOG_TRACKER,
    Permission.VIEW_GLOBAL_RBAC,
    Permission.MANAGE_GLOBAL_RBAC,
    Permission.VIEW_USERS,
    Permission.CREATE_USERS,
    Permission.DELETE_USERS,
    Permission.RENAME_USERS,
    Permission.RESET_USER_PASSWORDS,
)

PROJECT_PERMISSIONS: tuple[Permission, ...] = tuple(
    permission for permission in Permission if permission not in GLOBAL_PERMISSIONS
)

_VIEWS: frozenset[Permission] = frozenset(
    {
        Permission.VIEW_ISSUES,
        Permission.VIEW_BACKLOG,
        Permission.VIEW_BOARD,
        Permission.VIEW_CALENDAR,
        Permission.VIEW_SPRINTS,
        Permission.VIEW_SCHEDULES,
    }
)

ROLE_SCOPE: dict[RoleCode, Scope] = {
    RoleCode.OWNER: Scope.GLOBAL,
    RoleCode.ADMIN: Scope.GLOBAL,
    RoleCode.MEMBER: Scope.GLOBAL,
    RoleCode.CUSTOM: Scope.GLOBAL,
    RoleCode.PROJECT_OWNER: Scope.PROJECT,
    RoleCode.CONTRIBUTOR: Scope.PROJECT,
    RoleCode.VIEWER: Scope.PROJECT,
}

# A project write counts only when this global permission is held as well.
# The global permission does not itself grant the action in any project.
NECESSARY_GLOBAL: dict[Permission, Permission] = {
    Permission.CREATE_ISSUES: Permission.MAY_CREATE_ISSUES,
    Permission.EDIT_ISSUES: Permission.MAY_EDIT_ISSUES,
    Permission.DELETE_ISSUES: Permission.MAY_DELETE_ISSUES,
    Permission.COMMENT_ISSUES: Permission.MAY_CREATE_COMMENTS,
    Permission.DELETE_OWN_COMMENTS: Permission.MAY_DELETE_COMMENTS,
    Permission.DELETE_ANY_COMMENTS: Permission.MAY_DELETE_COMMENTS,
    Permission.CREATE_SCHEDULES: Permission.MAY_CREATE_SCHEDULES,
    Permission.EDIT_SCHEDULES: Permission.MAY_EDIT_SCHEDULES,
    Permission.DELETE_SCHEDULES: Permission.MAY_DELETE_SCHEDULES,
    Permission.CREATE_SPRINTS: Permission.MAY_CREATE_SPRINTS,
    Permission.EDIT_SPRINTS: Permission.MAY_EDIT_SPRINTS,
    Permission.DELETE_SPRINTS: Permission.MAY_DELETE_SPRINTS,
}

ROLE_PERMISSIONS: dict[RoleCode, frozenset[Permission]] = {
    RoleCode.OWNER: frozenset(),
    RoleCode.ADMIN: frozenset(GLOBAL_PERMISSIONS),
    RoleCode.MEMBER: frozenset(
        {
            Permission.VIEW_PROJECTS,
            Permission.MAY_CREATE_ISSUES,
            Permission.MAY_EDIT_ISSUES,
            Permission.MAY_CREATE_COMMENTS,
            Permission.MAY_CREATE_SCHEDULES,
            Permission.MAY_EDIT_SCHEDULES,
        }
    ),
    RoleCode.CUSTOM: frozenset(),
    RoleCode.VIEWER: _VIEWS,
    RoleCode.CONTRIBUTOR: _VIEWS
    | frozenset(
        {
            Permission.CREATE_ISSUES,
            Permission.EDIT_ISSUES,
            Permission.UPDATE_ISSUES,
            Permission.COMMENT_ISSUES,
            Permission.DELETE_OWN_COMMENTS,
            Permission.MANAGE_DEPENDENCIES,
        }
    ),
    RoleCode.PROJECT_OWNER: frozenset(PROJECT_PERMISSIONS),
}

ROLE_LABELS: dict[RoleCode, str] = {
    RoleCode.OWNER: "Owner",
    RoleCode.ADMIN: "Admin",
    RoleCode.MEMBER: "Member",
    RoleCode.CUSTOM: "Custom",
    RoleCode.PROJECT_OWNER: "Project Owner",
    RoleCode.CONTRIBUTOR: "Contributor",
    RoleCode.VIEWER: "Viewer",
}

DAY_ONE_OWNER_USERNAME = "jacob_hootman"
DAY_ONE_OWNER_PROJECTS: tuple[str, ...] = ("BOAT", "HOUSE", "KEEL", "PERSONAL")
DAY_ONE_CONTRIBUTORS: tuple[tuple[str, str], ...] = (
    ("Cursor", "KEEL"),
    ("danielle_hootman", "HOUSE"),
)


def permission_scope(permission: Permission) -> Scope:
    if permission in GLOBAL_PERMISSIONS:
        return Scope.GLOBAL
    return Scope.PROJECT


def parse_permission(code: str) -> Permission | None:
    try:
        return Permission(code)
    except ValueError:
        return None


def parse_role(code: str) -> RoleCode | None:
    try:
        return RoleCode(code)
    except ValueError:
        return None


def close(selected: frozenset[Permission]) -> frozenset[Permission]:
    """Add every dependency of the selected permissions, transitively."""
    result = set(selected)
    changed = True
    while changed:
        changed = False
        for permission in tuple(result):
            for required in DEPENDENCIES.get(permission, frozenset()):
                if required not in result:
                    result.add(required)
                    changed = True
    return frozenset(result)


def apply_direct_grants(
    previous: frozenset[Permission],
    submitted: frozenset[Permission],
) -> frozenset[Permission]:
    """Apply a checkbox edit, then close the set.

    Unchecking a permission also drops anything that depended on it.
    Checking a permission adds the permissions it requires.
    """
    removed = previous - submitted
    result = set(previous)
    result -= removed
    result |= submitted - previous
    strip = set(removed)
    changed = True
    while changed:
        changed = False
        for permission in tuple(result):
            needed = DEPENDENCIES.get(permission, frozenset())
            if needed & strip:
                result.discard(permission)
                strip.add(permission)
                changed = True
    return close(frozenset(result))


def resolve_global_roles(
    *,
    requested_owner: bool,
    requested_admin: bool,
    requested_custom: bool,
    actor_is_owner: bool,
    target_is_owner: bool,
    other_owners: int,
) -> frozenset[RoleCode]:
    """The global roles to store after a save.

    Member is the default. Custom replaces Member and holds no permissions
    of its own. Owner and Admin replace both. Only an Owner may change
    Owner membership, and the last Owner stays.
    """
    if requested_owner != target_is_owner and not actor_is_owner:
        raise OwnerChangeDeniedError("Only an Owner can grant or revoke Owner.")
    if target_is_owner and not requested_owner and other_owners < 1:
        raise LastOwnerError("The last Owner cannot be removed.")
    roles: set[RoleCode] = set()
    if requested_owner:
        roles.add(RoleCode.OWNER)
    if requested_admin:
        roles.add(RoleCode.ADMIN)
    if not roles:
        roles.add(RoleCode.CUSTOM if requested_custom else RoleCode.MEMBER)
    return frozenset(roles)


def satisfied(held: frozenset[Permission]) -> frozenset[Permission]:
    """Drop a permission whose dependency is not in the same set."""
    result = set(held)
    changed = True
    while changed:
        changed = False
        for permission in tuple(result):
            needed = DEPENDENCIES.get(permission, frozenset())
            if not needed <= result:
                result.discard(permission)
                changed = True
    return frozenset(result)


def effective_global(
    roles: frozenset[RoleCode],
    direct: frozenset[Permission],
) -> tuple[bool, frozenset[Permission]]:
    """Owner bypass, otherwise role bundles plus direct global grants."""
    if RoleCode.OWNER in roles:
        return True, frozenset(GLOBAL_PERMISSIONS)
    held: set[Permission] = set()
    for role in roles:
        if ROLE_SCOPE[role] is Scope.GLOBAL:
            held |= ROLE_PERMISSIONS[role]
    held |= {permission for permission in direct if permission in GLOBAL_PERMISSIONS}
    return False, satisfied(frozenset(held))


def effective_project(
    global_roles: frozenset[RoleCode],
    project_roles: frozenset[RoleCode],
    direct: frozenset[Permission],
) -> tuple[bool, frozenset[Permission]]:
    """Owner bypasses the project.

    Other global roles do not add project permissions. Creating, editing, or
    deleting issues, schedules, or sprints, and creating or deleting comments,
    still needs the matching global permission.
    """
    if RoleCode.OWNER in global_roles:
        return True, frozenset(PROJECT_PERMISSIONS)
    held: set[Permission] = set()
    for role in project_roles:
        if ROLE_SCOPE[role] is Scope.PROJECT:
            held |= ROLE_PERMISSIONS[role]
    held |= {permission for permission in direct if permission in PROJECT_PERMISSIONS}
    _is_owner, global_held = effective_global(global_roles, direct)
    allowed: set[Permission] = set()
    for permission in satisfied(frozenset(held)):
        gate = NECESSARY_GLOBAL.get(permission)
        if gate is None or gate in global_held:
            allowed.add(permission)
    return False, frozenset(allowed)
