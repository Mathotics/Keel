from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from keel.paths import license_text
from keel.web.layout import html_page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root() -> str:
    main = """\
      <h1>Keel</h1>
"""
    return html_page(title="Keel", main=main)


@router.get("/license", response_class=HTMLResponse)
def license_page() -> str:
    body = escape(license_text())
    main = f"""\
      <h1>License</h1>
      <pre class="keel-license">{body}</pre>
"""
    return html_page(title="License", main=main)
