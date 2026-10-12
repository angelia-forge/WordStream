from pydantic import BaseModel


class StatisticsSummary(BaseModel):
    total_events: int
    learned_days: int
    streak: int
