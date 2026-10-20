from fastapi import APIRouter

from keel.web.routes import (
    access,
    account,
    admin,
    backlog,
    board,
    forms,
    issues,
    lookup,
    pages,
    project_access,
    projects,
    schedules,
    search,
    sprints,
    users,
)

router = APIRouter()
router.include_router(account.router)
router.include_router(admin.router)
router.include_router(access.router)
router.include_router(pages.router)
router.include_router(search.router)
router.include_router(projects.router)
router.include_router(project_access.router)
router.include_router(board.router)
router.include_router(board.project_router)
router.include_router(backlog.router)
router.include_router(sprints.router)
router.include_router(schedules.router)
router.include_router(issues.router)
router.include_router(users.router)
router.include_router(forms.router)
router.include_router(lookup.router)
