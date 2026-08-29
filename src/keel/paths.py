from pathlib import Path


def assets_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / "assets",
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
