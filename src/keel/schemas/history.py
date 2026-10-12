from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HistoryEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_name: str
    field: str
    from_value: str
    to_value: str
    created_at: datetime
