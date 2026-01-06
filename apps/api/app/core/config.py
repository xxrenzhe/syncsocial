from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="dev", alias="APP_ENV")
    database_url: str = Field(
        default="postgresql+psycopg://syncsocial:syncsocial@localhost:5432/syncsocial",
        alias="DATABASE_URL",
    )

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=14, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    refresh_token_pepper: str = Field(default="change-me", alias="REFRESH_TOKEN_PEPPER")

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS")

    def normalized_cors_origins(self) -> list[str]:
        value: Any = self.cors_origins
        if isinstance(value, str):
            candidates = [part.strip() for part in value.split(",") if part.strip()]
            return candidates
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


settings = Settings()

