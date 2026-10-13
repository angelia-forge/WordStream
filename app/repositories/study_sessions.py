from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.learning import (
    LearningEvent,
    ReviewState,
    SessionAttempt,
    SessionItem,
    StudySession,
)


class StudySessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, study_session: StudySession) -> None:
        self._session.add(study_session)
        self._session.flush()

    def add_items(self, items: Sequence[SessionItem]) -> None:
        self._session.add_all(items)
        self._session.flush()

    def add_attempt(self, attempt: SessionAttempt) -> None:
        self._session.add(attempt)

    def add_learning_event(self, event: LearningEvent) -> None:
        self._session.add(event)

    def get_learning_events_by_client_ids(
        self,
        client_event_ids: Sequence[str],
    ) -> Sequence[LearningEvent]:
        if not client_event_ids:
            return []
        statement = select(LearningEvent).where(
            LearningEvent.client_event_id.in_(client_event_ids)
        )
        return list(self._session.scalars(statement))

    def get_learning_events_by_item_ids(
        self,
        session_item_ids: Sequence[str],
    ) -> Sequence[LearningEvent]:
        if not session_item_ids:
            return []
        statement = select(LearningEvent).where(
            LearningEvent.session_item_id.in_(session_item_ids)
        )
        return list(self._session.scalars(statement))

    def get(self, session_id: int) -> StudySession | None:
        statement = (
            select(StudySession)
            .options(
                selectinload(StudySession.items).selectinload(SessionItem.attempts)
            )
            .where(StudySession.id == session_id)
        )
        return self._session.scalar(statement)

    def get_active(self, vocabulary_id: int) -> StudySession | None:
        statement = (
            select(StudySession)
            .options(selectinload(StudySession.items))
            .where(
                StudySession.vocabulary_id == vocabulary_id,
                StudySession.status == "active",
            )
        )
        return self._session.scalar(statement)

    def get_review_state(self, entry_id: int) -> ReviewState | None:
        statement = select(ReviewState).where(ReviewState.entry_id == entry_id)
        with self._session.no_autoflush:
            return self._session.scalar(statement)

    def add_review_state(self, state: ReviewState) -> None:
        self._session.add(state)

    def flush(self) -> None:
        self._session.flush()
