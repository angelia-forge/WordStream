from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.learning import LearningEvent, ReviewState
from app.models.vocabulary import Entry


class LearningRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def event_count(self) -> int:
        return (
            self._session.scalar(select(func.count()).select_from(LearningEvent)) or 0
        )

    def activity_dates(
        self,
        *,
        vocabulary_id: int | None = None,
    ) -> Sequence[date]:
        statement = (
            select(LearningEvent.activity_date)
            .distinct()
            .order_by(LearningEvent.activity_date.desc())
        )
        if vocabulary_id is not None:
            statement = statement.where(
                LearningEvent.vocabulary_snapshot["id"].as_integer() == vocabulary_id
            )
        return list(self._session.scalars(statement))

    def distinct_terms_on(
        self,
        activity_date: date,
        *,
        vocabulary_id: int | None = None,
    ) -> int:
        statement = select(func.count(func.distinct(LearningEvent.term_key))).where(
            LearningEvent.activity_date == activity_date
        )
        if vocabulary_id is not None:
            statement = statement.where(
                LearningEvent.vocabulary_snapshot["id"].as_integer() == vocabulary_id
            )
        return self._session.scalar(statement) or 0

    def due_review_count(
        self,
        *,
        now: datetime,
        vocabulary_id: int | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(ReviewState)
            .join(Entry, Entry.id == ReviewState.entry_id)
            .where(
                ReviewState.next_review_at.is_not(None),
                ReviewState.next_review_at <= now,
            )
        )
        if vocabulary_id is not None:
            statement = statement.where(Entry.vocabulary_id == vocabulary_id)
        return self._session.scalar(statement) or 0

    def entry_count(self, *, vocabulary_id: int | None = None) -> int:
        statement = select(func.count()).select_from(Entry)
        if vocabulary_id is not None:
            statement = statement.where(Entry.vocabulary_id == vocabulary_id)
        return self._session.scalar(statement) or 0
