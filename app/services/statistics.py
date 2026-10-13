from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.schemas.statistics import (
    StatisticsSummary,
    TodayReviewsRead,
    TodayStatisticsRead,
)
from app.services.settings import get_or_create_setting
from app.unit_of_work import AbstractUnitOfWork


class StatisticsService:
    def __init__(self, uow: AbstractUnitOfWork, config: Settings) -> None:
        self._uow = uow
        self._config = config

    def summary(
        self,
        *,
        today: date | None = None,
    ) -> StatisticsSummary:
        with self._uow:
            setting = get_or_create_setting(self._uow, self._config)
            reference_date = today or local_date_at(utc_now(), setting.timezone)
            activity_dates = self._uow.learning.activity_dates()
            result = StatisticsSummary(
                total_events=self._uow.learning.event_count(),
                learned_days=len(activity_dates),
                streak=calculate_streak(activity_dates, reference_date),
            )
            self._uow.commit()
            return result

    def today(
        self,
        *,
        vocabulary_id: int | None = None,
        now: datetime | None = None,
    ) -> TodayStatisticsRead:
        reference_time = now or utc_now()
        with self._uow:
            setting = get_or_create_setting(self._uow, self._config)
            reference_date = local_date_at(reference_time, setting.timezone)
            activity_dates = self._uow.learning.activity_dates(
                vocabulary_id=vocabulary_id
            )
            result = TodayStatisticsRead(
                date=reference_date,
                timezone=setting.timezone,
                vocabulary_id=vocabulary_id,
                learned_terms=self._uow.learning.distinct_terms_on(
                    reference_date,
                    vocabulary_id=vocabulary_id,
                ),
                streak=calculate_streak(activity_dates, reference_date),
                total_entries=self._uow.learning.entry_count(
                    vocabulary_id=vocabulary_id
                ),
            )
            self._uow.commit()
            return result

    def reviews_today(
        self,
        *,
        vocabulary_id: int | None = None,
        now: datetime | None = None,
    ) -> TodayReviewsRead:
        reference_time = now or utc_now()
        with self._uow:
            result = TodayReviewsRead(
                as_of=reference_time,
                vocabulary_id=vocabulary_id,
                due_reviews=self._uow.learning.due_review_count(
                    now=reference_time,
                    vocabulary_id=vocabulary_id,
                ),
            )
            return result


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_date_at(moment: datetime, timezone: str) -> date:
    return moment.astimezone(ZoneInfo(timezone)).date()


def calculate_streak(activity_dates: Iterable[date], today: date) -> int:
    dates = set(activity_dates)
    cursor = today if today in dates else today - timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
