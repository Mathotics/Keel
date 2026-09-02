from fastapi import APIRouter

from keel.web.routes import (
    backlog,
    board,
    forms,
    issues,
    pages,
    projects,
    search,
    sprints,
    users,
)

router = APIRouter()
router.include_router(pages.router)
router.include_router(search.router)
router.include_router(projects.router)
router.include_router(board.router)
router.include_router(backlog.router)
router.include_router(sprints.router)
router.include_router(issues.router)
router.include_router(users.router)
router.include_router(forms.router)
