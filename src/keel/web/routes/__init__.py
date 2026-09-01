from fastapi import APIRouter

from keel.web.routes import forms, pages, users

router = APIRouter()
router.include_router(pages.router)
router.include_router(users.router)
router.include_router(forms.router)
