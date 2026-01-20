from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformPublic(BaseModel):
    platform_key: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=64)
    login_url: str = Field(min_length=1, max_length=500)
    capabilities: list[str]

