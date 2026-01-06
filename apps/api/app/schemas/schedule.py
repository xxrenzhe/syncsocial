from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SchedulePublic(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    enabled: bool
    strategy_id: UUID
    account_selector: dict
    frequency: str
    schedule_spec: dict
    random_config: dict
    max_parallel: int
    next_run_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    strategy_id: UUID
    enabled: bool = True
    account_selector: dict = Field(default_factory=dict)
    frequency: str = Field(default="manual", max_length=32)
    schedule_spec: dict = Field(default_factory=dict)
    random_config: dict = Field(default_factory=dict)
    max_parallel: int = Field(default=1, ge=1, le=100)


class UpdateScheduleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    account_selector: dict | None = None
    frequency: str | None = Field(default=None, max_length=32)
    schedule_spec: dict | None = None
    random_config: dict | None = None
    max_parallel: int | None = Field(default=None, ge=1, le=100)

