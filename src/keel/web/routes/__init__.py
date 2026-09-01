from fastapi import APIRouter

from keel.web.routes import forms, issues, pages, projects, users

router = APIRouter()
router.include_router(pages.router)
router.include_router(projects.router)
router.include_router(issues.router)
router.include_router(users.router)
router.include_router(forms.router)
