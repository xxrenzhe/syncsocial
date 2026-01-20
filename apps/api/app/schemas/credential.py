from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.social_account import SocialAccountPublic


class ImportCredentialRequest(BaseModel):
    credential_type: str = Field(default="storage_state", min_length=1, max_length=32)
    storage_state: dict | None = None
    cookies: list[dict] | None = None


class ImportCredentialResponse(BaseModel):
    account: SocialAccountPublic
    health_check_status: str
    error_code: str | None = None
    message: str | None = None
