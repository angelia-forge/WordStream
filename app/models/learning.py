from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.setting import utc_now


class StudyPlan(Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        UniqueConstraint("vocabulary_id", name="uq_study_plans_vocabulary_id"),
        CheckConstraint(
            "daily_new_count >= 0 AND daily_new_count <= 500",
            name="daily_new_count_range",
        ),
        CheckConstraint(
            "daily_review_count >= 0 AND daily_review_count <= 500",
            name="daily_review_count_range",
        ),
        CheckConstraint(
            "interval_seconds >= 1 AND interval_seconds <= 10",
            name="interval_seconds_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabularies.id", ondelete="CASCADE"),
        nullable=False,
    )
    daily_new_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
    )
    daily_review_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
    )
    interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    is_random: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_loop: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'finished', 'abandoned')",
            name="status_allowed",
        ),
        CheckConstraint("current_index >= 0", name="current_index_non_negative"),
        Index("ix_study_sessions_vocabulary_id", "vocabulary_id"),
        Index(
            "uq_study_sessions_active_vocabulary",
            "vocabulary_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plans.id", ondelete="SET NULL"),
    )
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabularies.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    items: Mapped[list[SessionItem]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SessionItem.position",
    )


class SessionItem(Base):
    __tablename__ = "session_items"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("source IN ('review', 'new')", name="source_allowed"),
        CheckConstraint(
            "result IS NULL OR result IN ('seen', 'again')",
            name="result_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        Index("ix_session_items_session_position", "session_id", "position"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    session: Mapped[StudySession] = relationship(back_populates="items")
    attempts: Mapped[list[SessionAttempt]] = relationship(
        back_populates="session_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SessionAttempt(Base):
    __tablename__ = "session_attempts"
    __table_args__ = (
        CheckConstraint(
            "action IN ('seen', 'again', 'replayed')",
            name="action_allowed",
        ),
        Index("ix_session_attempts_session_item_id", "session_item_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_item_id: Mapped[str] = mapped_column(
        ForeignKey("session_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    session_item: Mapped[SessionItem] = relationship(back_populates="attempts")


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (
        UniqueConstraint("entry_id", name="uq_review_states_entry_id"),
        CheckConstraint(
            "box_number >= 0 AND box_number <= 4",
            name="box_number_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    box_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint("result IN ('seen', 'again')", name="result_allowed"),
        CheckConstraint("attempt_count > 0", name="attempt_count_positive"),
        CheckConstraint(
            "client_attempt_count > 0",
            name="client_attempt_count_positive",
        ),
        Index("ix_learning_events_activity_date", "activity_date"),
        Index("ix_learning_events_entry_id", "entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_event_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )
    session_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("session_items.id", ondelete="SET NULL"),
        unique=True,
    )
    entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("entries.id", ondelete="SET NULL"),
    )
    term_key: Mapped[str] = mapped_column(String(500), nullable=False)
    term_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    vocabulary_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    client_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
