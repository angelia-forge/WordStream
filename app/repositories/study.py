from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning import ReviewState, StudyPlan
from app.models.vocabulary import Entry


class StudyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_plan(self, vocabulary_id: int) -> StudyPlan | None:
        statement = select(StudyPlan).where(StudyPlan.vocabulary_id == vocabulary_id)
        return self._session.scalar(statement)

    def add_plan(self, plan: StudyPlan) -> None:
        self._session.add(plan)
        self._session.flush()

    def list_due_reviews(
        self,
        vocabulary_id: int,
        *,
        now: datetime,
    ) -> Sequence[Entry]:
        statement = (
            select(Entry)
            .join(ReviewState, ReviewState.entry_id == Entry.id)
            .where(
                Entry.vocabulary_id == vocabulary_id,
                ReviewState.next_review_at.is_not(None),
                ReviewState.next_review_at <= now,
            )
            .order_by(ReviewState.next_review_at.asc(), Entry.id.asc())
        )
        return list(self._session.scalars(statement))

    def list_new_entries(self, vocabulary_id: int) -> Sequence[Entry]:
        statement = (
            select(Entry)
            .outerjoin(ReviewState, ReviewState.entry_id == Entry.id)
            .where(
                Entry.vocabulary_id == vocabulary_id,
                ReviewState.id.is_(None),
            )
            .order_by(Entry.created_at.asc(), Entry.id.asc())
        )
        return list(self._session.scalars(statement))
