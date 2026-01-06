from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SocialAccountPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    platform_key: str
    handle: str | None
    display_name: str | None
    status: str
    labels: dict
    created_at: datetime
    updated_at: datetime
    last_health_check_at: datetime | None


class CreateSocialAccountRequest(BaseModel):
    platform_key: str = Field(min_length=1, max_length=32)
    handle: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    labels: dict = Field(default_factory=dict)

