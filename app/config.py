from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DISABLED = "disabled"
    PASSWORD = "password"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WordStream"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    database_url: str = "sqlite:///./data/wordstream.db"
    app_timezone: str = "Asia/Shanghai"

    auth_mode: AuthMode = AuthMode.DISABLED
    app_password_hash: SecretStr | None = None
    secret_key: SecretStr | None = None
    app_api_key: SecretStr | None = None
    session_cookie_name: str = "wordstream_session"
    session_max_age_seconds: int = 43_200

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_security(self) -> Settings:
        if self.environment is Environment.PRODUCTION:
            if self.auth_mode is AuthMode.DISABLED:
                raise ValueError("Authentication cannot be disabled in production")
            if self.secret_key is None:
                raise ValueError("SECRET_KEY is required in production")
        if self.auth_mode is AuthMode.PASSWORD and (
            self.app_password_hash is None or self.secret_key is None
        ):
            raise ValueError(
                "APP_PASSWORD_HASH and SECRET_KEY are required for password auth"
            )
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
