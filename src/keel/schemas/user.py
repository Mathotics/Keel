from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)
    username: str | None = Field(default=None, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    created_at: datetime
    updated_at: datetime


class ProfileRead(UserRead):
    """The signed-in person's profile, including optional contact fields.

    The user list stays on ``UserRead`` and does not carry these fields.
    """

    email: str
    first_name: str
    last_name: str
    date_of_birth: date | None


class ProfileUpdate(BaseModel):
    """``display_name`` and ``username`` are required.

    The contact fields follow partial update: leave one out and it stays,
    send null or a blank string to clear it.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)


class TokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)


class TokenLabelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)


class LoginCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=100)


class LoginRead(BaseModel):
    token: str
    token_id: int
    label: str
    username: str
    display_name: str


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None


class TokenCreated(TokenRead):
    token: str
