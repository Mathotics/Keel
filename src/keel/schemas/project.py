from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9]{1,9}$"


class ProjectCreate(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str
    created_at: datetime
