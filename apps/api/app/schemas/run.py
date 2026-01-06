from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.action import ActionPublic


class RunPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    schedule_id: UUID | None
    strategy_id: UUID
    triggered_by: UUID | None
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AccountRunPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    run_id: UUID
    social_account_id: UUID
    status: str
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


class RunDetail(BaseModel):
    run: RunPublic
    account_runs: list[AccountRunPublic]
    actions: list[ActionPublic] = []
