from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from pydantic.config import ConfigDict


class ArtifactPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    action_id: UUID
    type: str
    storage_key: str
    size: int | None
    created_at: datetime

