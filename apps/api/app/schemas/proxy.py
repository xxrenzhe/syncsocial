from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProxyPoolPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    strategy: str
    created_at: datetime
    updated_at: datetime


class CreateProxyPoolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    strategy: str = Field(default="hash", min_length=1, max_length=32)


class UpdateProxyPoolRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    strategy: str | None = Field(default=None, min_length=1, max_length=32)


class ProxyPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    pool_id: UUID
    scheme: str
    host: str
    port: int
    country: str | None
    enabled: bool
    weight: int
    consecutive_failures: int
    last_error_code: str | None
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateProxyRequest(BaseModel):
    scheme: str = Field(default="http", min_length=1, max_length=16)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    country: str | None = Field(default=None, max_length=2)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    weight: int = Field(default=1, ge=1, le=100)


class UpdateProxyRequest(BaseModel):
    scheme: str | None = Field(default=None, min_length=1, max_length=16)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    country: str | None = Field(default=None, max_length=2)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    weight: int | None = Field(default=None, ge=1, le=100)

