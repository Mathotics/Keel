from pathlib import Path

from platformdirs import user_data_dir


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]


def assets_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        _repo_root() / "assets",
        here.parent / "assets",
    )
    for path in candidates:
        if path.is_dir():
            return path
    raise FileNotFoundError("assets directory not found")


def asset_path(name: str) -> Path:
    path = assets_dir() / name
    if not path.is_file():
        raise FileNotFoundError(f"asset not found: {name}")
    return path


def license_path() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        _repo_root() / "LICENSE",
        here.parent / "LICENSE",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("LICENSE not found")


def license_text() -> str:
    return license_path().read_text(encoding="utf-8")


def copyright_notice() -> str:
    first = license_text().splitlines()[0].strip()
    if not first:
        raise FileNotFoundError("LICENSE is missing a copyright line")
    return first


def templates_dir() -> Path:
    """Jinja2 templates, which ship inside the package."""
    path = Path(__file__).resolve().parent / "web" / "templates"
    if not path.is_dir():
        raise FileNotFoundError("templates directory not found")
    return path


def migrations_dir() -> Path:
    """The Alembic environment, which lives beside the package."""
    here = Path(__file__).resolve()
    candidates = (
        _repo_root() / "migrations",
        here.parent / "migrations",
    )
    for path in candidates:
        if path.is_dir():
            return path
    raise FileNotFoundError("migrations directory not found")


def data_dir() -> Path:
    """Where Keel keeps the database, independent of the working directory."""
    return Path(user_data_dir(appname="Keel", appauthor=False))


def database_path() -> Path:
    return data_dir() / "keel.db"
