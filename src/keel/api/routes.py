from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from keel import __version__

router = APIRouter()

_ROOT_PAGE = """\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Keel</title>
    <link rel="icon" href="/assets/favicon.ico" type="image/x-icon"/>
    <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon"/>
  </head>
  <body>
    <main>
      <p><img src="/assets/favicon.ico" width="64" height="64" alt="Keel"/></p>
      <h1>Keel</h1>
      <p>version {version}</p>
    </main>
  </body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def root() -> str:
    return _ROOT_PAGE.format(version=__version__)
