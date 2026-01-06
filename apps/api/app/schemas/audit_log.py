from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    actor_user_id: UUID | None
    actor_email: str | None = None
    action: str
    target_type: str | None
    target_id: UUID | None
    metadata: dict
    created_at: datetime

