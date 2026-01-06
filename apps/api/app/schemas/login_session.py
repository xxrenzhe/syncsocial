from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LoginSessionPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    social_account_id: UUID
    platform_key: str
    status: str
    remote_url: str | None
    expires_at: datetime
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

