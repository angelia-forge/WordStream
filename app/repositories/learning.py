from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.learning import LearningEvent


class LearningRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def event_count(self) -> int:
        return (
            self._session.scalar(select(func.count()).select_from(LearningEvent)) or 0
        )

    def activity_dates(self) -> Sequence[date]:
        statement = (
            select(LearningEvent.activity_date)
            .distinct()
            .order_by(LearningEvent.activity_date.desc())
        )
        return list(self._session.scalars(statement))
