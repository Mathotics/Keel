from fastapi import APIRouter

from keel.api.v1 import boards, issues, projects, users

router = APIRouter(prefix="/api/v1")
router.include_router(users.router)
router.include_router(projects.router)
router.include_router(issues.router)
router.include_router(boards.router)
