from __future__ import annotations

from collections.abc import MutableSequence
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from zoneinfo import ZoneInfo

from app.config import Settings
from app.exceptions import AppError
from app.models.learning import (
    LearningEvent,
    ReviewState,
    SessionAttempt,
    SessionItem,
    StudySession,
)
from app.models.setting import utc_now
from app.schemas.study_sessions import (
    OutcomeBatch,
    OutcomeBatchResult,
    OutcomeWrite,
    SessionEntrySnapshot,
    SessionItemRead,
    SessionState,
    StudySessionCreate,
    StudySessionRead,
    StudySessionSummary,
)
from app.services.study_plans import assemble_queue
from app.unit_of_work import AbstractUnitOfWork

T = TypeVar("T")
REVIEW_INTERVAL_DAYS = (1, 3, 7, 14, 30)


class StudySessionService:
    def __init__(
        self,
        uow: AbstractUnitOfWork,
        settings: Settings,
    ) -> None:
        self._uow = uow
        self._settings = settings

    def create(self, command: StudySessionCreate) -> StudySessionRead:
        with self._uow:
            vocabulary = self._uow.vocabularies.get(command.vocabulary_id)
            if vocabulary is None:
                raise AppError(
                    "RESOURCE_NOT_FOUND",
                    "Vocabulary was not found",
                    status_code=404,
                )
            plan = self._uow.study.get_plan(command.vocabulary_id)
            if plan is None:
                raise AppError(
                    "PLAN_REQUIRED",
                    "Configure a study plan before starting",
                    status_code=409,
                )

            active = self._uow.study_sessions.get_active(command.vocabulary_id)
            if active is not None and command.resume_existing:
                return self._serialize(active)
            if active is not None:
                active.status = "abandoned"
                active.finished_at = utc_now()
                self._uow.study_sessions.flush()

            now = utc_now()
            due_reviews = self._uow.study.list_due_reviews(
                command.vocabulary_id,
                now=now,
            )
            new_entries = self._uow.study.list_new_entries(command.vocabulary_id)
            queue = assemble_queue(
                due_reviews,
                new_entries,
                daily_review_count=plan.daily_review_count,
                daily_new_count=plan.daily_new_count,
                is_random=plan.is_random,
            )
            if not queue:
                raise AppError(
                    "EMPTY_STUDY_QUEUE",
                    "No entries are available for this study plan",
                    status_code=409,
                )

            entries = {entry.id: entry for entry in [*due_reviews, *new_entries]}
            study_session = StudySession(
                plan_id=plan.id,
                vocabulary_id=vocabulary.id,
                status="active",
                started_at=now,
                current_index=0,
                plan_snapshot={
                    "daily_new_count": plan.daily_new_count,
                    "daily_review_count": plan.daily_review_count,
                    "interval_seconds": plan.interval_seconds,
                    "is_random": plan.is_random,
                    "is_loop": plan.is_loop,
                    "vocabulary_name": vocabulary.name,
                },
            )
            self._uow.study_sessions.add(study_session)
            session_items = []
            for position, queue_item in enumerate(queue):
                entry = entries[queue_item.entry_id]
                session_items.append(
                    SessionItem(
                        session_id=study_session.id,
                        entry_id=entry.id,
                        position=position,
                        source=queue_item.kind,
                        entry_snapshot={
                            "term": entry.term,
                            "normalized_term": entry.normalized_term,
                            "part_of_speech": entry.part_of_speech,
                            "phonetic": entry.phonetic,
                            "meaning": entry.meaning,
                            "example": entry.example,
                        },
                    )
                )
            self._uow.study_sessions.add_items(session_items)
            study_session.items = session_items
            self._uow.commit()
            return self._serialize(study_session)

    def get(self, session_id: int) -> StudySessionRead:
        with self._uow:
            return self._serialize(self._require_session(session_id))

    def record_outcomes(
        self,
        session_id: int,
        batch: OutcomeBatch,
    ) -> OutcomeBatchResult:
        with self._uow:
            study_session = self._require_active_session(session_id)
            now = utc_now()
            self._validate_batch_times(batch, now)

            items_by_id = {item.id: item for item in study_session.items}
            for outcome in batch.outcomes:
                if outcome.session_item_id not in items_by_id:
                    raise AppError(
                        "SESSION_ITEM_NOT_FOUND",
                        "Session item does not belong to this session",
                        status_code=404,
                    )

            attempt_ids = [str(outcome.attempt_id) for outcome in batch.outcomes]
            persisted = {
                attempt.id: attempt
                for attempt in self._uow.study_sessions.get_attempts(attempt_ids)
            }
            self._validate_idempotency(batch.outcomes, persisted)

            accepted = 0
            duplicates = 0
            processed: set[str] = set()
            for outcome in batch.outcomes:
                attempt_id = str(outcome.attempt_id)
                if attempt_id in persisted or attempt_id in processed:
                    duplicates += 1
                    continue
                self._apply_outcome(study_session, outcome)
                self._uow.study_sessions.add_attempt(
                    SessionAttempt(
                        id=attempt_id,
                        session_item_id=outcome.session_item_id,
                        action=outcome.action,
                        occurred_at=outcome.occurred_at,
                    )
                )
                processed.add(attempt_id)
                accepted += 1

            self._uow.commit()
            state = self._serialize(study_session)
            return OutcomeBatchResult(
                **state.model_dump(),
                accepted=accepted,
                duplicates=duplicates,
            )

    def finish(self, session_id: int) -> StudySessionSummary:
        with self._uow:
            study_session = self._require_session(session_id)
            if study_session.status == "abandoned":
                raise AppError(
                    "SESSION_NOT_ACTIVE",
                    "An abandoned session cannot be finished",
                    status_code=409,
                )
            if study_session.status == "active":
                finished_at = utc_now()
                for item in study_session.items:
                    if item.result is not None:
                        self._write_learning_result(
                            study_session,
                            item,
                            finished_at,
                        )
                study_session.status = "finished"
                study_session.finished_at = finished_at
                self._uow.commit()
            return self._summary(study_session)

    def _apply_outcome(
        self,
        study_session: StudySession,
        outcome: OutcomeWrite,
    ) -> None:
        items = sorted(study_session.items, key=lambda item: item.position)
        if study_session.current_index >= len(items):
            raise AppError(
                "SESSION_COMPLETE",
                "All session items have already been processed",
                status_code=409,
            )
        current = items[study_session.current_index]
        if current.id != outcome.session_item_id:
            raise AppError(
                "OUTCOME_OUT_OF_ORDER",
                "Outcome does not match the current session item",
                status_code=409,
                details={"expected_session_item_id": current.id},
            )

        if outcome.action == "seen":
            if current.result is not None:
                raise AppError(
                    "OUTCOME_ALREADY_RECORDED",
                    "The final result for this item is already recorded",
                    status_code=409,
                )
            current.result = "seen"
            study_session.current_index += 1
        elif outcome.action == "again":
            if current.result == "seen":
                raise AppError(
                    "OUTCOME_ALREADY_RECORDED",
                    "The final result for this item is already recorded",
                    status_code=409,
                )
            if current.result is None:
                current.result = "again"
            move_current_for_retry(items, study_session.current_index)
            for position, item in enumerate(items):
                item.position = position
            study_session.items = items
        else:
            if current.result != "again":
                raise AppError(
                    "INVALID_REPLAY",
                    "Only an item marked again can be replayed",
                    status_code=409,
                )
            study_session.current_index += 1
        current.attempt_count += 1

    def _write_learning_result(
        self,
        study_session: StudySession,
        item: SessionItem,
        finished_at: datetime,
    ) -> None:
        occurred_at = max(
            (_as_utc(attempt.occurred_at) for attempt in item.attempts),
            default=finished_at,
        )
        local_date = occurred_at.astimezone(
            ZoneInfo(self._settings.app_timezone)
        ).date()
        snapshot = item.entry_snapshot
        self._uow.study_sessions.add_learning_event(
            LearningEvent(
                session_item_id=item.id,
                entry_id=item.entry_id,
                term_key=str(snapshot["normalized_term"]),
                term_snapshot=str(snapshot["term"]),
                vocabulary_id_snapshot=study_session.vocabulary_id,
                vocabulary_name_snapshot=str(
                    study_session.plan_snapshot["vocabulary_name"]
                ),
                result=item.result,
                attempts=item.attempt_count,
                occurred_at=occurred_at,
                timezone=self._settings.app_timezone,
                activity_date=local_date,
            )
        )
        state = self._uow.study_sessions.get_review_state(item.entry_id)
        if state is None:
            state = ReviewState(entry_id=item.entry_id, box_number=1)
            self._uow.study_sessions.add_review_state(state)
        if item.result == "again":
            state.box_number = 1
        else:
            state.box_number = min(state.box_number + 1, 5)
        state.last_reviewed_at = occurred_at
        state.next_review_at = occurred_at + timedelta(
            days=REVIEW_INTERVAL_DAYS[state.box_number - 1]
        )

    @staticmethod
    def _validate_batch_times(batch: OutcomeBatch, now: datetime) -> None:
        lower = now - timedelta(hours=24)
        upper = now + timedelta(hours=24)
        if any(not lower <= outcome.occurred_at <= upper for outcome in batch.outcomes):
            raise AppError(
                "VALIDATION_ERROR",
                "occurred_at must be within 24 hours of server time",
                status_code=422,
            )

    @staticmethod
    def _validate_idempotency(
        outcomes: list[OutcomeWrite],
        persisted: dict[str, SessionAttempt],
    ) -> None:
        payloads: dict[str, tuple[str, str, datetime]] = {}
        for outcome in outcomes:
            attempt_id = str(outcome.attempt_id)
            payload = (
                outcome.session_item_id,
                outcome.action,
                outcome.occurred_at,
            )
            previous = payloads.get(attempt_id)
            if previous is not None and previous != payload:
                raise AppError(
                    "IDEMPOTENCY_CONFLICT",
                    "attempt_id was reused with different content",
                    status_code=409,
                )
            payloads[attempt_id] = payload
            existing = persisted.get(attempt_id)
            if existing is not None and (
                existing.session_item_id != outcome.session_item_id
                or existing.action != outcome.action
                or _as_utc(existing.occurred_at) != outcome.occurred_at
            ):
                raise AppError(
                    "IDEMPOTENCY_CONFLICT",
                    "attempt_id was reused with different content",
                    status_code=409,
                )

    @staticmethod
    def _serialize(study_session: StudySession) -> StudySessionRead:
        return StudySessionRead(
            session=SessionState.model_validate(study_session),
            items=[
                SessionItemRead(
                    id=item.id,
                    entry_id=item.entry_id,
                    position=item.position,
                    source=item.source,
                    attempt_count=item.attempt_count,
                    result=item.result,
                    entry=SessionEntrySnapshot.model_validate(item.entry_snapshot),
                )
                for item in sorted(
                    study_session.items,
                    key=lambda candidate: candidate.position,
                )
            ],
        )

    @staticmethod
    def _summary(study_session: StudySession) -> StudySessionSummary:
        items = study_session.items
        if study_session.finished_at is None:
            raise RuntimeError("Finished session is missing finished_at")
        return StudySessionSummary(
            session_id=study_session.id,
            status="finished",
            total_items=len(items),
            completed_items=sum(item.result is not None for item in items),
            seen_items=sum(item.result == "seen" for item in items),
            again_items=sum(item.result == "again" for item in items),
            total_attempts=sum(item.attempt_count for item in items),
            finished_at=study_session.finished_at,
        )

    def _require_session(self, session_id: int) -> StudySession:
        study_session = self._uow.study_sessions.get(session_id)
        if study_session is None:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Study session was not found",
                status_code=404,
            )
        return study_session

    def _require_active_session(self, session_id: int) -> StudySession:
        study_session = self._require_session(session_id)
        if study_session.status != "active":
            raise AppError(
                "SESSION_NOT_ACTIVE",
                "Study session is not active",
                status_code=409,
            )
        return study_session


def move_current_for_retry(items: MutableSequence[T], current_index: int) -> int:
    if current_index < 0 or current_index >= len(items):
        raise IndexError("current_index is outside the queue")
    item = items.pop(current_index)
    target_index = min(current_index + 2, len(items))
    items.insert(target_index, item)
    return target_index


def remaining_milliseconds(
    deadline_ms: float,
    now_ms: float,
) -> float:
    return max(0.0, deadline_ms - now_ms)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
