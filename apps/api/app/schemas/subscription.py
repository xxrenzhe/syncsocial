from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceSubscriptionPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    status: str
    plan_key: str
    seats: int
    max_social_accounts: int | None
    max_parallel_sessions: int | None
    automation_runtime_hours: int | None
    artifact_retention_days: int | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkspaceUsageMonthlyPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    period_start: date
    automation_runtime_seconds: int
    created_at: datetime
    updated_at: datetime


class AdminUpsertWorkspaceSubscriptionRequest(BaseModel):
    status: str = Field(default="trial", max_length=32)
    plan_key: str = Field(default="trial", max_length=64)
    seats: int = Field(default=1, ge=1, le=10_000)
    max_social_accounts: int | None = Field(default=None, ge=0, le=1_000_000)
    max_parallel_sessions: int | None = Field(default=None, ge=0, le=10_000)
    automation_runtime_hours: int | None = Field(default=None, ge=0, le=10_000_000)
    artifact_retention_days: int | None = Field(default=None, ge=0, le=10_000)
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None


class AdminSubscriptionOverview(BaseModel):
    subscription: WorkspaceSubscriptionPublic | None
    current_month_usage: WorkspaceUsageMonthlyPublic | None
    active: bool
    active_reason: str | None = None

