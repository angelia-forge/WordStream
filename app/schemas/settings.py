from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timezone: str
    tts_rate: float
    default_interval_seconds: int
    daily_goal: int
    updated_at: datetime


class AppSettingUpdate(BaseModel):
    timezone: str | None = None
    tts_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    default_interval_seconds: int | None = Field(default=None, ge=2, le=60)
    daily_goal: int | None = Field(default=None, ge=0, le=500)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value
