from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from keel.domain.enums import NotificationType


class NoticeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    type: NotificationType
    actor_id: int | None
    actor_name: str
    issue_id: int | None
    issue_key: str
    issue_title: str
    body: str
    read_at: datetime | None
    created_at: datetime
    deliver_at: datetime | None


class PreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: NotificationType
    email: bool
    phone: bool
    bell: bool


class PreferenceReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferences: list[PreferenceRead] = Field(min_length=7, max_length=7)


class PhoneSetupRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    subscribe_url: str | None = None


class PhoneTokenWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
