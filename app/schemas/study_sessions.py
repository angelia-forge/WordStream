from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SessionStatus = Literal["active", "finished", "abandoned"]
SessionSource = Literal["review", "new"]
SessionResult = Literal["seen", "again"]


class StudySessionCreate(BaseModel):
    vocabulary_id: int = Field(gt=0)
    resume_existing: bool = True


class SessionState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int | None
    vocabulary_id: int
    status: SessionStatus
    started_at: datetime
    finished_at: datetime | None
    current_index: int
    plan_snapshot: dict[str, Any]

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def normalize_sqlite_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class SessionEntrySnapshot(BaseModel):
    term: str
    normalized_term: str
    part_of_speech: str | None
    phonetic: str | None
    meaning: str
    example: str | None


class SessionItemRead(BaseModel):
    id: str
    entry_id: int
    position: int
    source: SessionSource
    attempt_count: int
    result: SessionResult | None
    entry: SessionEntrySnapshot


class StudySessionRead(BaseModel):
    session: SessionState
    items: list[SessionItemRead]


class OutcomeWrite(BaseModel):
    session_item_id: str
    client_event_id: UUID
    result: SessionResult
    attempt_count: int = Field(ge=1)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(UTC)


class OutcomeBatch(BaseModel):
    outcomes: list[OutcomeWrite] = Field(min_length=1, max_length=100)


class OutcomeBatchResult(StudySessionRead):
    accepted: int
    duplicates: int


class StudySessionSummary(BaseModel):
    session_id: int
    status: Literal["finished"]
    total_items: int
    completed_items: int
    seen_items: int
    again_items: int
    total_attempts: int
    finished_at: datetime

    @field_validator("finished_at", mode="before")
    @classmethod
    def normalize_sqlite_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
