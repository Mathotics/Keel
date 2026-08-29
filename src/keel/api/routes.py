from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from keel import __version__
from keel.web.layout import html_page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root() -> str:
    main = f"""\
      <h1>Keel</h1>
      <p>version {__version__}</p>
"""
    return html_page(title="Keel", main=main)
