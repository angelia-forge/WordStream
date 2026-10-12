from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.setting import utc_now


class StudyPlan(Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        UniqueConstraint("vocabulary_id", name="uq_study_plans_vocabulary_id"),
        CheckConstraint("daily_new_limit > 0", name="daily_new_limit_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabularies.id", ondelete="CASCADE"),
        nullable=False,
    )
    daily_new_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (
        UniqueConstraint("entry_id", name="uq_review_states_entry_id"),
        CheckConstraint(
            "box_number >= 1 AND box_number <= 5",
            name="box_number_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    box_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint("attempts > 0", name="attempts_positive"),
        Index("ix_learning_events_activity_date", "activity_date"),
        Index("ix_learning_events_entry_id", "entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("entries.id", ondelete="SET NULL"),
    )
    term_key: Mapped[str] = mapped_column(String(500), nullable=False)
    term_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    vocabulary_id_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    vocabulary_name_snapshot: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="seen")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
