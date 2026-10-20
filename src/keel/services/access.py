"""Load and store roles and direct grants.

Global checks are enforced by callers. Project route checks are a later story;
this module still stores project roles so that story has the rows it needs.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from keel.db.models import (
    PermissionDependency,
    PermissionRow,
    Project,
    ProjectEveryonePermission,
    ProjectEveryoneRole,
    Role,
    RolePermission,
    User,
    UserPermission,
    UserRole,
)
from keel.domain.access import (
    DAY_ONE_CONTRIBUTORS,
    DAY_ONE_OWNER_PROJECTS,
    DAY_ONE_OWNER_USERNAME,
    DEPENDENCIES,
    GLOBAL_PERMISSIONS,
    LABELS,
    PROJECT_PERMISSIONS,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    ROLE_SCOPE,
    Permission,
    RoleCode,
    Scope,
    apply_direct_grants,
    effective_global,
    effective_project,
    parse_permission,
    parse_role,
    permission_scope,
    resolve_global_roles,
)
from keel.domain.errors import (
    LastProjectOwnerError,
    NotFoundError,
    PermissionDeniedError,
)
from keel.services import auth as auth_service
from keel.services import users as user_service
from keel.services.passwords import verify_password

DENIED = "You are signed in, but this action is not allowed."


@dataclass(frozen=True)
class Access:
    """What the signed-in person may do, for this request."""

    user_id: int | None
    is_owner: bool
    global_permissions: frozenset[str]
    project_ids: frozenset[int]

    def allows(self, permission: str) -> bool:
        if self.is_owner:
            return True
        return permission in self.global_permissions


EMPTY_ACCESS = Access(
    user_id=None,
    is_owner=False,
    global_permissions=frozenset(),
    project_ids=frozenset(),
)


@dataclass(frozen=True)
class GlobalGrant:
    user_id: int
    username: str
    display_name: str
    roles: frozenset[RoleCode]
    direct: frozenset[Permission]


def seed_catalog(session: Session) -> None:
    """Insert the catalog and refresh role bundles. Direct grants stay."""
    by_code = _permission_rows(session)
    for permission in Permission:
        permission_row = by_code.get(permission.value)
        scope = permission_scope(permission).value
        if permission_row is None:
            permission_row = PermissionRow(code=permission.value, scope=scope)
            session.add(permission_row)
            session.flush()
            by_code[permission.value] = permission_row
        elif permission_row.scope != scope:
            permission_row.scope = scope
    session.execute(delete(PermissionDependency))
    for permission, required_set in DEPENDENCIES.items():
        for required in required_set:
            session.add(
                PermissionDependency(
                    permission_id=by_code[permission.value].id,
                    requires_id=by_code[required.value].id,
                )
            )
    roles = _role_rows(session)
    for code, scope in ROLE_SCOPE.items():
        role_row = roles.get(code.value)
        bypass = code is RoleCode.OWNER
        if role_row is None:
            role_row = Role(code=code.value, scope=scope.value, bypass=bypass)
            session.add(role_row)
            session.flush()
            roles[code.value] = role_row
        else:
            role_row.scope = scope.value
            role_row.bypass = bypass
    session.execute(delete(RolePermission))
    for code, permissions in ROLE_PERMISSIONS.items():
        role = roles[code.value]
        for permission in permissions:
            session.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=by_code[permission.value].id,
                )
            )
    session.flush()


def ensure_global_roles(session: Session) -> None:
    """Give every person a global role, and the server an Owner.

    A person with no global role becomes Member. When nobody is Owner, Owner
    goes to jacob_hootman if that account exists, otherwise to the earliest
    user. This does not rewrite project roles.
    """
    seed_catalog(session)
    people = list(user_service.list_users(session))
    for person in people:
        if not global_roles(session, person.id):
            replace_global_roles(session, person.id, frozenset({RoleCode.MEMBER}))
    if _owner_count(session) == 0 and people:
        named = user_service.find_by_username(session, DAY_ONE_OWNER_USERNAME)
        target = named or user_service.first_user(session)
        if target is not None:
            replace_global_roles(session, target.id, frozenset({RoleCode.OWNER}))


def assign_day_one(session: Session) -> None:
    """The grants for the current server. Safe to run once, on upgrade."""
    ensure_global_roles(session)
    owner = user_service.find_by_username(session, DAY_ONE_OWNER_USERNAME)
    if owner is not None:
        replace_global_roles(session, owner.id, frozenset({RoleCode.OWNER}))
        for key in DAY_ONE_OWNER_PROJECTS:
            project = _project_by_key(session, key)
            if project is not None:
                set_project_role(session, owner.id, project.id, RoleCode.PROJECT_OWNER)
    for username, key in DAY_ONE_CONTRIBUTORS:
        person = user_service.find_by_username(session, username)
        project = _project_by_key(session, key)
        if person is None or project is None:
            continue
        if owner is None or person.id != owner.id:
            _keep_member(session, person.id)
        set_project_role(session, person.id, project.id, RoleCode.CONTRIBUTOR)


def grant_default_global_role(session: Session, user: User) -> None:
    """A new person is Member until someone assigns Owner or Admin."""
    seed_catalog(session)
    if not global_roles(session, user.id):
        replace_global_roles(session, user.id, frozenset({RoleCode.MEMBER}))


def load_access(session: Session, user_id: int | None) -> Access:
    if user_id is None:
        return EMPTY_ACCESS
    roles = global_roles(session, user_id)
    direct = global_direct(session, user_id)
    is_owner, held = effective_global(roles, direct)
    return Access(
        user_id=user_id,
        is_owner=is_owner,
        global_permissions=frozenset(permission.value for permission in held),
        project_ids=_project_ids(session, user_id),
    )


def require(access: Access, permission: Permission) -> None:
    if not access.allows(permission.value):
        raise PermissionDeniedError(DENIED)


def global_grants(session: Session) -> list[GlobalGrant]:
    rows: list[GlobalGrant] = []
    for person in user_service.list_users(session):
        rows.append(
            GlobalGrant(
                user_id=person.id,
                username=person.username,
                display_name=person.display_name,
                roles=global_roles(session, person.id),
                direct=global_direct(session, person.id),
            )
        )
    return rows


def save_global_grant(
    session: Session,
    actor: Access,
    user_id: int,
    *,
    requested_owner: bool,
    requested_admin: bool,
    requested_editor: bool,
    requested_custom: bool,
    requested_no_access: bool,
    submitted_direct: frozenset[Permission],
) -> GlobalGrant:
    require(actor, Permission.MANAGE_GLOBAL_RBAC)
    person = user_service.get_user(session, user_id)
    current = global_roles(session, person.id)
    target_is_owner = RoleCode.OWNER in current
    others = _owner_count(session)
    if target_is_owner:
        others -= 1
    roles = resolve_global_roles(
        requested_owner=requested_owner,
        requested_admin=requested_admin,
        requested_editor=requested_editor,
        requested_custom=requested_custom,
        requested_no_access=requested_no_access,
        actor_is_owner=actor.is_owner,
        target_is_owner=target_is_owner,
        other_owners=others,
    )
    if RoleCode.NO_ACCESS in roles:
        direct: frozenset[Permission] = frozenset()
        _clear_project_assignments(session, person.id)
    else:
        previous = global_direct(session, person.id)
        direct = apply_direct_grants(
            previous,
            frozenset(item for item in submitted_direct if item in GLOBAL_PERMISSIONS),
        )
    replace_global_roles(session, person.id, roles)
    replace_global_direct(session, person.id, direct)
    return GlobalGrant(
        user_id=person.id,
        username=person.username,
        display_name=person.display_name,
        roles=roles,
        direct=direct,
    )


def set_project_role(
    session: Session,
    user_id: int,
    project_id: int,
    role: RoleCode,
) -> None:
    if ROLE_SCOPE[role] is not Scope.PROJECT:
        raise NotFoundError("That role is not a project role.")
    seed_catalog(session)
    session.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.project_id == project_id,
        )
    )
    role_row = _require_role(session, role)
    session.add(
        UserRole(user_id=user_id, role_id=role_row.id, project_id=project_id),
    )
    session.flush()


def project_role(session: Session, user_id: int, project_id: int) -> RoleCode | None:
    code = session.scalar(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, UserRole.project_id == project_id)
    )
    if code is None:
        return None
    parsed = parse_role(code)
    if parsed is None or ROLE_SCOPE[parsed] is not Scope.PROJECT:
        return None
    return parsed


def project_direct(
    session: Session, user_id: int, project_id: int
) -> frozenset[Permission]:
    return _project_permission_codes(
        session.scalars(
            select(PermissionRow.code)
            .join(UserPermission, UserPermission.permission_id == PermissionRow.id)
            .where(
                UserPermission.user_id == user_id,
                UserPermission.project_id == project_id,
            )
        ).all()
    )


def everyone_role(session: Session, project_id: int) -> RoleCode | None:
    code = session.scalar(
        select(Role.code)
        .join(ProjectEveryoneRole, ProjectEveryoneRole.role_id == Role.id)
        .where(ProjectEveryoneRole.project_id == project_id)
    )
    if code is None:
        return None
    parsed = parse_role(code)
    if parsed is None or ROLE_SCOPE[parsed] is not Scope.PROJECT:
        return None
    return parsed


def everyone_direct(session: Session, project_id: int) -> frozenset[Permission]:
    return _project_permission_codes(
        session.scalars(
            select(PermissionRow.code)
            .join(
                ProjectEveryonePermission,
                ProjectEveryonePermission.permission_id == PermissionRow.id,
            )
            .where(ProjectEveryonePermission.project_id == project_id)
        ).all()
    )


def holds_project(
    session: Session,
    actor: Access,
    project_id: int,
    permission: Permission,
) -> bool:
    if actor.user_id is None:
        return False
    _bypass, held = _held_project(session, actor, project_id)
    return _bypass or permission in held


def require_project(
    session: Session,
    actor: Access,
    project_id: int,
    permission: Permission,
) -> None:
    if not holds_project(session, actor, project_id, permission):
        raise PermissionDeniedError(DENIED)


def save_project_grant(
    session: Session,
    actor: Access,
    project_id: int,
    user_id: int,
    *,
    role: RoleCode | None,
    submitted_direct: frozenset[Permission],
) -> None:
    require_project(session, actor, project_id, Permission.MANAGE_PROJECT_RBAC)
    user_service.get_user(session, user_id)
    if role is not None and ROLE_SCOPE[role] is not Scope.PROJECT:
        raise NotFoundError("That role is not a project role.")
    _keep_a_project_owner(
        session,
        actor,
        project_id,
        named_delta=_owner_delta(project_role(session, user_id, project_id), role),
        everyone_is_owner=everyone_role(session, project_id) is RoleCode.PROJECT_OWNER,
    )
    direct = apply_direct_grants(
        project_direct(session, user_id, project_id),
        frozenset(item for item in submitted_direct if item in PROJECT_PERMISSIONS),
    )
    _replace_project_role(session, user_id, project_id, role)
    _replace_project_direct(session, user_id, project_id, direct)


def save_everyone_grant(
    session: Session,
    actor: Access,
    project_id: int,
    *,
    role: RoleCode | None,
    submitted_direct: frozenset[Permission],
) -> None:
    require_project(session, actor, project_id, Permission.MANAGE_PROJECT_RBAC)
    if role is not None and ROLE_SCOPE[role] is not Scope.PROJECT:
        raise NotFoundError("That role is not a project role.")
    _keep_a_project_owner(
        session,
        actor,
        project_id,
        named_delta=0,
        everyone_is_owner=role is RoleCode.PROJECT_OWNER,
    )
    direct = apply_direct_grants(
        everyone_direct(session, project_id),
        frozenset(item for item in submitted_direct if item in PROJECT_PERMISSIONS),
    )
    _replace_everyone_role(session, project_id, role)
    _replace_everyone_direct(session, project_id, direct)


def assert_may_delete_user(session: Session, actor: Access, user_id: int) -> None:
    """Deleting an Owner is an Owner change. The last Owner stays."""
    require(actor, Permission.DELETE_USERS)
    if RoleCode.OWNER not in global_roles(session, user_id):
        return
    if not actor.is_owner:
        from keel.domain.errors import OwnerChangeDeniedError

        raise OwnerChangeDeniedError("Only an Owner can grant or revoke Owner.")
    if _owner_count(session) - 1 < 1:
        from keel.domain.errors import LastOwnerError

        raise LastOwnerError("The last Owner cannot be removed.")


def reset_user_password(
    session: Session,
    actor: Access,
    user_id: int,
    password: str,
    confirm: str,
) -> None:
    require(actor, Permission.RESET_USER_PASSWORDS)
    if actor.user_id == user_id:
        from keel.domain.errors import InvalidPasswordError

        raise InvalidPasswordError("Change your own password from your profile.")
    person = user_service.get_user(session, user_id)
    from keel.domain.errors import InvalidPasswordError, PasswordMismatchError

    if password != confirm:
        raise PasswordMismatchError("The new passwords do not match.")
    if person.password_hash and verify_password(person.password_hash, password):
        raise InvalidPasswordError("Choose a different password.")
    user_service.set_password(session, person, password)
    auth_service.revoke_sessions(session, person.id)


def visible_project_ids(access: Access, projects: list[Project]) -> list[Project]:
    if access.is_owner or access.allows(Permission.VIEW_PROJECTS.value):
        return projects
    return [project for project in projects if project.id in access.project_ids]


def global_roles(session: Session, user_id: int) -> frozenset[RoleCode]:
    codes = session.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, UserRole.project_id.is_(None))
    ).all()
    found: set[RoleCode] = set()
    for code in codes:
        parsed = parse_role(code)
        if parsed is not None and ROLE_SCOPE[parsed] is Scope.GLOBAL:
            found.add(parsed)
    return frozenset(found)


def global_direct(session: Session, user_id: int) -> frozenset[Permission]:
    codes = session.scalars(
        select(PermissionRow.code)
        .join(UserPermission, UserPermission.permission_id == PermissionRow.id)
        .where(
            UserPermission.user_id == user_id,
            UserPermission.project_id.is_(None),
        )
    ).all()
    found: set[Permission] = set()
    for code in codes:
        parsed = parse_permission(code)
        if parsed is not None and parsed in GLOBAL_PERMISSIONS:
            found.add(parsed)
    return frozenset(found)


def replace_global_roles(
    session: Session,
    user_id: int,
    roles: frozenset[RoleCode],
) -> None:
    session.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.project_id.is_(None),
        )
    )
    for role in roles:
        if ROLE_SCOPE[role] is not Scope.GLOBAL:
            continue
        session.add(
            UserRole(
                user_id=user_id,
                role_id=_require_role(session, role).id,
                project_id=None,
            )
        )
    session.flush()


def _clear_project_assignments(session: Session, user_id: int) -> None:
    """Remove project roles and project grants. No Access keeps none of them."""
    session.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.project_id.is_not(None),
        )
    )
    session.execute(
        delete(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.project_id.is_not(None),
        )
    )
    session.flush()


def replace_global_direct(
    session: Session,
    user_id: int,
    permissions: frozenset[Permission],
) -> None:
    session.execute(
        delete(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.project_id.is_(None),
        )
    )
    for permission in permissions:
        if permission not in GLOBAL_PERMISSIONS:
            continue
        session.add(
            UserPermission(
                user_id=user_id,
                permission_id=_require_permission(session, permission).id,
                project_id=None,
            )
        )
    session.flush()


_CATALOG_ROLES: tuple[RoleCode, ...] = (
    RoleCode.OWNER,
    RoleCode.ADMIN,
    RoleCode.EDITOR,
    RoleCode.MEMBER,
    RoleCode.CUSTOM,
    RoleCode.NO_ACCESS,
    RoleCode.VIEWER,
    RoleCode.CONTRIBUTOR,
    RoleCode.PROJECT_OWNER,
)
_PERMISSION_ORDER: tuple[Permission, ...] = GLOBAL_PERMISSIONS + PROJECT_PERMISSIONS


@dataclass(frozen=True)
class CatalogRole:
    """One role and the permissions it includes, for the Access page."""

    label: str
    scope: str
    permissions: str


@dataclass(frozen=True)
class CatalogPermission:
    """One permission and the permission it requires, for the Access page."""

    code: str
    label: str
    scope: str
    requires: str


def _scope_label(scope: Scope) -> str:
    if scope == Scope.GLOBAL:
        return "Global"
    return "Project"


def _joined(permissions: frozenset[Permission]) -> str:
    names = [LABELS[item] for item in _PERMISSION_ORDER if item in permissions]
    return ", ".join(names)


def _requires(permission: Permission) -> str:
    return _joined(DEPENDENCIES.get(permission, frozenset()))


def _requires_codes(permission: Permission) -> str:
    needed = DEPENDENCIES.get(permission, frozenset())
    return " ".join(item.value for item in _PERMISSION_ORDER if item in needed)


def access_catalog() -> tuple[tuple[CatalogRole, ...], tuple[CatalogPermission, ...]]:
    """Roles with the permissions they include, then each permission's requirement."""
    roles: list[CatalogRole] = []
    for code in _CATALOG_ROLES:
        if code == RoleCode.OWNER:
            included = "Bypasses every global and project permission"
        else:
            included = _joined(ROLE_PERMISSIONS[code]) or "None"
        roles.append(
            CatalogRole(
                label=ROLE_LABELS[code],
                scope=_scope_label(ROLE_SCOPE[code]),
                permissions=included,
            )
        )
    permissions = tuple(
        CatalogPermission(
            code=permission.value,
            label=LABELS[permission],
            scope=_scope_label(permission_scope(permission)),
            requires=_requires(permission) or "None",
        )
        for permission in _PERMISSION_ORDER
    )
    return tuple(roles), permissions


def permission_choices() -> list[tuple[str, str, str, str]]:
    return [_choice(permission) for permission in GLOBAL_PERMISSIONS]


def project_permission_choices() -> list[tuple[str, str, str, str]]:
    return [_choice(permission) for permission in PROJECT_PERMISSIONS]


def _choice(permission: Permission) -> tuple[str, str, str, str]:
    return (
        permission.value,
        LABELS[permission],
        _requires(permission),
        _requires_codes(permission),
    )


def role_label(code: RoleCode) -> str:
    return ROLE_LABELS[code]


def _keep_member(session: Session, user_id: int) -> None:
    roles = global_roles(session, user_id)
    if RoleCode.OWNER in roles or RoleCode.ADMIN in roles:
        return
    if roles != frozenset({RoleCode.MEMBER}):
        replace_global_roles(session, user_id, frozenset({RoleCode.MEMBER}))


def _owner_count(session: Session) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == RoleCode.OWNER.value, UserRole.project_id.is_(None))
    )
    return int(count or 0)


def _project_ids(session: Session, user_id: int) -> frozenset[int]:
    if RoleCode.NO_ACCESS in global_roles(session, user_id):
        return frozenset()
    from_roles = session.scalars(
        select(UserRole.project_id).where(
            UserRole.user_id == user_id,
            UserRole.project_id.is_not(None),
        )
    ).all()
    from_grants = session.scalars(
        select(UserPermission.project_id).where(
            UserPermission.user_id == user_id,
            UserPermission.project_id.is_not(None),
        )
    ).all()
    from_everyone_roles = session.scalars(select(ProjectEveryoneRole.project_id)).all()
    from_everyone_grants = session.scalars(
        select(ProjectEveryonePermission.project_id)
    ).all()
    return frozenset(
        project_id
        for project_id in (
            *from_roles,
            *from_grants,
            *from_everyone_roles,
            *from_everyone_grants,
        )
        if project_id
    )


def _held_project(
    session: Session, actor: Access, project_id: int
) -> tuple[bool, frozenset[Permission]]:
    assert actor.user_id is not None
    roles = global_roles(session, actor.user_id)
    personal = project_role(session, actor.user_id, project_id)
    project_roles = frozenset({personal}) if personal is not None else frozenset()
    direct = global_direct(session, actor.user_id) | project_direct(
        session, actor.user_id, project_id
    )
    return effective_project(
        roles,
        project_roles,
        direct,
        everyone_role=everyone_role(session, project_id),
        everyone_direct=everyone_direct(session, project_id),
    )


def _owner_delta(current: RoleCode | None, new: RoleCode | None) -> int:
    was = current is RoleCode.PROJECT_OWNER
    will = new is RoleCode.PROJECT_OWNER
    if was and not will:
        return -1
    if will and not was:
        return 1
    return 0


def _keep_a_project_owner(
    session: Session,
    actor: Access,
    project_id: int,
    *,
    named_delta: int,
    everyone_is_owner: bool,
) -> None:
    if actor.is_owner:
        return
    named = session.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.project_id == project_id,
            Role.code == RoleCode.PROJECT_OWNER.value,
        )
    )
    remaining = int(named or 0) + named_delta + (1 if everyone_is_owner else 0)
    if remaining < 1:
        raise LastProjectOwnerError("The last Project Owner cannot be removed.")


def _replace_project_role(
    session: Session,
    user_id: int,
    project_id: int,
    role: RoleCode | None,
) -> None:
    session.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.project_id == project_id,
        )
    )
    if role is not None:
        session.add(
            UserRole(
                user_id=user_id,
                role_id=_require_role(session, role).id,
                project_id=project_id,
            )
        )
    session.flush()


def _replace_project_direct(
    session: Session,
    user_id: int,
    project_id: int,
    permissions: frozenset[Permission],
) -> None:
    session.execute(
        delete(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.project_id == project_id,
        )
    )
    for permission in permissions:
        if permission not in PROJECT_PERMISSIONS:
            continue
        session.add(
            UserPermission(
                user_id=user_id,
                permission_id=_require_permission(session, permission).id,
                project_id=project_id,
            )
        )
    session.flush()


def _replace_everyone_role(
    session: Session, project_id: int, role: RoleCode | None
) -> None:
    session.execute(
        delete(ProjectEveryoneRole).where(ProjectEveryoneRole.project_id == project_id)
    )
    if role is not None:
        session.add(
            ProjectEveryoneRole(
                project_id=project_id,
                role_id=_require_role(session, role).id,
            )
        )
    session.flush()


def _replace_everyone_direct(
    session: Session,
    project_id: int,
    permissions: frozenset[Permission],
) -> None:
    session.execute(
        delete(ProjectEveryonePermission).where(
            ProjectEveryonePermission.project_id == project_id
        )
    )
    for permission in permissions:
        if permission not in PROJECT_PERMISSIONS:
            continue
        session.add(
            ProjectEveryonePermission(
                project_id=project_id,
                permission_id=_require_permission(session, permission).id,
            )
        )
    session.flush()


def _project_permission_codes(codes: Sequence[str]) -> frozenset[Permission]:
    found: set[Permission] = set()
    for code in codes:
        parsed = parse_permission(code)
        if parsed is not None and parsed in PROJECT_PERMISSIONS:
            found.add(parsed)
    return frozenset(found)


def _project_by_key(session: Session, key: str) -> Project | None:
    return session.scalars(select(Project).where(Project.key == key)).first()


def _permission_rows(session: Session) -> dict[str, PermissionRow]:
    rows = session.scalars(select(PermissionRow)).all()
    return {row.code: row for row in rows}


def _role_rows(session: Session) -> dict[str, Role]:
    rows = session.scalars(select(Role)).all()
    return {row.code: row for row in rows}


def _require_role(session: Session, role: RoleCode) -> Role:
    row = session.scalars(select(Role).where(Role.code == role.value)).first()
    if row is None:
        raise NotFoundError(f"No role {role.value}.")
    return row


def _require_permission(session: Session, permission: Permission) -> PermissionRow:
    row = session.scalars(
        select(PermissionRow).where(PermissionRow.code == permission.value)
    ).first()
    if row is None:
        raise NotFoundError(f"No permission {permission.value}.")
    return row
