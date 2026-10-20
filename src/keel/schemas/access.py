from pydantic import BaseModel, ConfigDict, Field


class GlobalGrantRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    username: str
    display_name: str
    roles: list[str]
    direct_permissions: list[str]


class GlobalGrantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: bool = False
    admin: bool = False
    editor: bool = False
    custom: bool = False
    no_access: bool = False
    direct_permissions: list[str] = Field(default_factory=list)


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=128)
    confirm: str = Field(min_length=1, max_length=128)
