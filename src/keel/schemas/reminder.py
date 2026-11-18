from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OffsetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = Field(ge=1)
    unit: Literal["minute", "hour", "day"]


class OverdueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["every_n", "daily_at"]
    amount: int | None = Field(default=None, ge=1)
    unit: Literal["minute", "hour", "day"] | None = None
    minute_of_day: int | None = Field(default=None, ge=0, le=1439)


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_offsets: list[OffsetBody] = Field(default_factory=list, max_length=20)
    at_start: bool = False
    due_offsets: list[OffsetBody] = Field(default_factory=list, max_length=20)
    at_due: bool = False
    overdue: OverdueBody | None = None


class RuleWrite(RuleBody):
    base_updated_at: datetime | None = None


class RuleRead(RuleBody):
    id: int
    scope: Literal["default", "series", "issue"]
    series_id: int | None = None
    issue_id: int | None = None
    updated_at: datetime


class RuleSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: RuleRead | None = None


class StateRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: int
    snooze_until: datetime | None
    overdue_dismissed: bool
    updated_at: datetime


class EffectiveRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["issue", "series", "default", "none"]
    rule: RuleBody | None
    own: RuleRead | None
    start_missing: bool
    due_missing: bool
    closed: bool
    snooze_until: datetime | None
    overdue_dismissed: bool
    state_updated_at: datetime | None


class BundleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: RuleRead | None
    series: list[RuleRead]
    issues: list[RuleRead]
    states: list[StateRead]


class FireRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: int
    issue_key: str
    issue_title: str
    at: datetime
    reasons: list[str]
    catch_up: bool


class SnoozeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    until: datetime
    base_updated_at: datetime | None = None


class StateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_updated_at: datetime | None = None
