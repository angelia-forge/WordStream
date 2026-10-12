from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.schemas.statistics import StatisticsSummary
from app.unit_of_work import AbstractUnitOfWork


class StatisticsService:
    def __init__(self, uow: AbstractUnitOfWork, config: Settings) -> None:
        self._uow = uow
        self._config = config

    def summary(self, *, today: date | None = None) -> StatisticsSummary:
        reference_date = today or self.local_today()
        with self._uow:
            activity_dates = self._uow.learning.activity_dates()
            return StatisticsSummary(
                total_events=self._uow.learning.event_count(),
                learned_days=len(activity_dates),
                streak=calculate_streak(activity_dates, reference_date),
            )

    def local_today(self) -> date:
        return datetime.now(ZoneInfo(self._config.app_timezone)).date()


def calculate_streak(activity_dates: Iterable[date], today: date) -> int:
    dates = set(activity_dates)
    cursor = today if today in dates else today - timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
