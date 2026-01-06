from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from app.schemas.artifact import ArtifactPublic


class ActionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    account_run_id: UUID
    action_type: str
    platform_key: str
    target_external_id: str | None
    target_url: str | None
    idempotency_key: str
    status: str
    error_code: str | None
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_", serialization_alias="metadata")
    artifacts: list[ArtifactPublic] = []
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
