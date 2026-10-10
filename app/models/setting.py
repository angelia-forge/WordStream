from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_id"),
        CheckConstraint("tts_rate >= 0.5 AND tts_rate <= 2.0", name="tts_rate"),
        CheckConstraint(
            "default_interval_seconds >= 2 AND default_interval_seconds <= 60",
            name="default_interval",
        ),
        CheckConstraint(
            "daily_goal >= 0 AND daily_goal <= 500",
            name="daily_goal",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    tts_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    default_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
    daily_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
