from datetime import date, datetime

from pydantic import BaseModel


class StatisticsSummary(BaseModel):
    total_events: int
    learned_days: int
    streak: int


class TodayStatisticsRead(BaseModel):
    date: date
    timezone: str
    vocabulary_id: int | None
    learned_terms: int
    streak: int
    total_entries: int


class TodayReviewsRead(BaseModel):
    as_of: datetime
    vocabulary_id: int | None
    due_reviews: int
