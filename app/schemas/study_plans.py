from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudyPlanUpdate(BaseModel):
    daily_new_count: int = Field(default=20, ge=0, le=500)
    daily_review_count: int = Field(default=20, ge=0, le=500)
    interval_seconds: int = Field(default=5, ge=1, le=10)
    is_random: bool = False
    is_loop: bool = False


class StudyPlanRead(StudyPlanUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vocabulary_id: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def normalize_sqlite_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


QueueItemKind = Literal["review", "new"]


class StudyQueueItem(BaseModel):
    entry_id: int
    term: str
    kind: QueueItemKind


class StudyQueue(BaseModel):
    vocabulary_id: int
    interval_seconds: int
    is_loop: bool
    items: list[StudyQueueItem]
