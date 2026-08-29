from keel.version import package_version


def html_page(*, title: str, main: str) -> str:
    """Keel HTML chrome: sticky top bar, content, sticky footer with version."""
    version_label = f"Keel {package_version()}"
    return f"""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{title}</title>
    <link rel="icon" href="/assets/favicon.ico" type="image/x-icon"/>
    <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon"/>
    <link rel="stylesheet" href="/assets/brand.css"/>
  </head>
  <body>
    <header class="keel-topbar">
      <a class="keel-topbar__home" href="/" aria-label="Keel home">
        <img src="/assets/small_icon.png" alt=""/>
      </a>
    </header>
    <main class="keel-main">
{main}
    </main>
    <footer class="keel-footer">
      <p class="keel-footer__version">{version_label}</p>
    </footer>
  </body>
</html>
"""
