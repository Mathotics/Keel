from fastapi import APIRouter

from keel.api.v1.deps import SessionDep
from keel.schemas.label import LabelRead
from keel.services import labels as label_service

router = APIRouter(prefix="/labels", tags=["labels"])


@router.get("", response_model=list[LabelRead])
def list_labels(session: SessionDep) -> list[LabelRead]:
    return [LabelRead.of(label) for label in label_service.list_labels(session)]
