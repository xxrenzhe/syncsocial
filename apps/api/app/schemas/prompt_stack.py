from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PromptStackPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    key: str
    version: int
    payload: dict
    created_at: datetime
    updated_at: datetime


class UpsertPromptStackRequest(BaseModel):
    payload: dict = Field(default_factory=dict)


class PromptStackPreviewRequest(BaseModel):
    payload: dict | None = None
    seed: int | None = None


class PromptStackPreviewResponse(BaseModel):
    text: str

