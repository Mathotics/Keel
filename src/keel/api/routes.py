from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from keel.web.layout import html_page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root() -> str:
    main = """\
      <h1>Keel</h1>
"""
    return html_page(title="Keel", main=main)
