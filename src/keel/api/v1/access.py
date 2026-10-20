from fastapi import APIRouter

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.domain.access import Permission, parse_permission
from keel.domain.errors import PermissionDeniedError
from keel.schemas.access import GlobalGrantRead, GlobalGrantUpdate
from keel.services import access as access_service
from keel.services.access import DENIED

router = APIRouter(prefix="/access", tags=["access"])


def _access(session: SessionDep, acting: ActingUserDep) -> access_service.Access:
    if acting is None:
        raise PermissionDeniedError(DENIED)
    return access_service.load_access(session, acting.id)


def _read(grant: access_service.GlobalGrant) -> GlobalGrantRead:
    return GlobalGrantRead(
        user_id=grant.user_id,
        username=grant.username,
        display_name=grant.display_name,
        roles=sorted(role.value for role in grant.roles),
        direct_permissions=sorted(permission.value for permission in grant.direct),
    )


@router.get("/global", response_model=list[GlobalGrantRead])
def list_global_grants(
    session: SessionDep,
    acting: ActingUserDep,
) -> list[GlobalGrantRead]:
    access = _access(session, acting)
    access_service.require(access, Permission.VIEW_GLOBAL_RBAC)
    return [_read(grant) for grant in access_service.global_grants(session)]


@router.put("/global/{user_id}", response_model=GlobalGrantRead)
def update_global_grant(
    user_id: int,
    payload: GlobalGrantUpdate,
    session: SessionDep,
    acting: ActingUserDep,
) -> GlobalGrantRead:
    access = _access(session, acting)
    submitted = set()
    for code in payload.direct_permissions:
        parsed = parse_permission(code)
        if parsed is not None:
            submitted.add(parsed)
    saved = access_service.save_global_grant(
        session,
        access,
        user_id,
        requested_owner=payload.owner,
        requested_admin=payload.admin,
        submitted_direct=frozenset(submitted),
    )
    return _read(saved)
