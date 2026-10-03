from fastapi import APIRouter

from keel.web.routes import (
    account,
    backlog,
    board,
    forms,
    issues,
    lookup,
    pages,
    projects,
    schedules,
    search,
    sprints,
    users,
)

router = APIRouter()
router.include_router(account.router)
router.include_router(pages.router)
router.include_router(search.router)
router.include_router(projects.router)
router.include_router(board.router)
router.include_router(board.project_router)
router.include_router(backlog.router)
router.include_router(sprints.router)
router.include_router(schedules.router)
router.include_router(issues.router)
router.include_router(users.router)
router.include_router(forms.router)
router.include_router(lookup.router)
