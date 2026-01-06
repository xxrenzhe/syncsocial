from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    internal_token: str = Field(default="change-me", alias="BROWSER_NODE_INTERNAL_TOKEN")
    novnc_public_url: str | None = Field(default=None, alias="NOVNC_PUBLIC_URL")
    headless: bool = Field(default=False, alias="BROWSER_NODE_HEADLESS")


settings = Settings()

