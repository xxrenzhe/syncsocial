from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    email: EmailStr
    display_name: str | None = None
    role: str
    status: str
    must_change_password: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="user")
    display_name: str | None = None
    temporary_password: str | None = None


class AdminCreateUserResponse(BaseModel):
    user: UserPublic
    initial_password: str | None = None


class AdminUpdateUserRequest(BaseModel):
    role: str | None = None
    status: str | None = None
    display_name: str | None = None


class ResetPasswordResponse(BaseModel):
    temporary_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12)

