from fastapi import APIRouter

from keel import __version__

router = APIRouter()


@router.get("/")
def root() -> dict[str, str]:
    return {"name": "keel", "version": __version__}
