from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StrategyPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    platform_key: str
    version: int
    config: dict
    created_at: datetime
    updated_at: datetime


class CreateStrategyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    platform_key: str = Field(min_length=1, max_length=32)
    config: dict = Field(default_factory=dict)


class UpdateStrategyRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    config: dict | None = None

