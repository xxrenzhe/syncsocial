from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceLlmConfigPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    provider: str
    base_url: str | None
    model: str | None
    has_api_key: bool
    created_at: datetime
    updated_at: datetime


class UpsertWorkspaceLlmConfigRequest(BaseModel):
    provider: str = Field(default="openai", min_length=1, max_length=32)
    api_key: str = Field(min_length=1, max_length=400)
    base_url: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=100)

