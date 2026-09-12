from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from keel.domain.enums import SprintCadence

KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9]{1,9}$"


class ProjectCreate(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    sprint_cadence: SprintCadence | None = None
    sprint_cadence_days: int | None = Field(default=None, ge=1)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str
    sprint_cadence: SprintCadence
    sprint_cadence_days: int | None
    created_at: datetime
