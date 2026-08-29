from pathlib import Path


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
