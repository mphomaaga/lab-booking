"""Login and user schemas."""

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel, RequestModel, UtcDateTime


class LoginRequest(RequestModel):
    student_number: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class User(ApiModel):
    id: int
    student_number: str
    is_admin: bool


class UserRef(ApiModel):
    id: int
    student_number: str


class LoginResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_at: UtcDateTime
    user: User
