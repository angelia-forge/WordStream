from __future__ import annotations

from collections.abc import MutableSequence
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, OperationalError

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
OUTCOME_WRITE_MAX_ATTEMPTS = 3


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
            now = utc_now()
            self._validate_batch_times(batch, now)
            unique_outcomes = self._deduplicate_batch(batch.outcomes)
            client_event_ids = [
                str(outcome.client_event_id) for outcome in unique_outcomes
            ]
            item_ids = [outcome.session_item_id for outcome in unique_outcomes]
            for attempt in range(OUTCOME_WRITE_MAX_ATTEMPTS):
                study_session = self._require_session(session_id)
                items_by_id = {item.id: item for item in study_session.items}
                for outcome in batch.outcomes:
                    if outcome.session_item_id not in items_by_id:
                        raise AppError(
                            "SESSION_ITEM_NOT_FOUND",
                            "Session item does not belong to this session",
                            status_code=404,
                        )

                events_by_client_id = {
                    event.client_event_id: event
                    for event in (
                        self._uow.study_sessions.get_learning_events_by_client_ids(
                            client_event_ids
                        )
                    )
                }
                events_by_item_id = {
                    event.session_item_id: event
                    for event in (
                        self._uow.study_sessions.get_learning_events_by_item_ids(
                            item_ids
                        )
                    )
                }
                self._validate_persisted_outcomes(
                    unique_outcomes,
                    events_by_client_id,
                    events_by_item_id,
                )
                new_outcomes = [
                    outcome
                    for outcome in unique_outcomes
                    if str(outcome.client_event_id) not in events_by_client_id
                ]
                if new_outcomes and study_session.status != "active":
                    raise AppError(
                        "SESSION_NOT_ACTIVE",
                        "Study session is not active",
                        status_code=409,
                    )
                setting = self._uow.settings.get() if new_outcomes else None
                event_timezone = (
                    setting.timezone
                    if setting is not None
                    else self._settings.app_timezone
                )

                accepted = 0
                duplicates = len(batch.outcomes) - len(unique_outcomes)
                for outcome in unique_outcomes:
                    client_event_id = str(outcome.client_event_id)
                    if client_event_id in events_by_client_id:
                        duplicates += 1
                        continue

                    item = items_by_id[outcome.session_item_id]
                    item.attempt_count += 1
                    item.result = outcome.result
                    self._uow.study_sessions.add_attempt(
                        SessionAttempt(
                            id=client_event_id,
                            session_item_id=outcome.session_item_id,
                            action=outcome.result,
                            occurred_at=outcome.occurred_at,
                        )
                    )
                    self._write_learning_result(
                        study_session,
                        item,
                        outcome,
                        timezone=event_timezone,
                    )
                    accepted += 1

                study_session.current_index = sum(
                    item.result is not None for item in study_session.items
                )
                try:
                    self._uow.study_sessions.flush()
                    self._uow.commit()
                except IntegrityError as exc:
                    self._uow.rollback()
                    race_events = {
                        event.client_event_id: event
                        for event in (
                            self._uow.study_sessions.get_learning_events_by_client_ids(
                                client_event_ids
                            )
                        )
                    }
                    race_item_events = {
                        event.session_item_id: event
                        for event in (
                            self._uow.study_sessions.get_learning_events_by_item_ids(
                                item_ids
                            )
                        )
                    }
                    self._validate_persisted_outcomes(
                        unique_outcomes,
                        race_events,
                        race_item_events,
                    )
                    if len(race_events) == len(unique_outcomes):
                        state = self._serialize(self._require_session(session_id))
                        return OutcomeBatchResult(
                            **state.model_dump(),
                            accepted=0,
                            duplicates=len(batch.outcomes),
                        )
                    if not race_events and not race_item_events:
                        raise
                    if attempt == OUTCOME_WRITE_MAX_ATTEMPTS - 1:
                        raise AppError(
                            "DATABASE_BUSY",
                            "Concurrent outcomes are still being recorded; "
                            "retry the batch",
                            status_code=503,
                        ) from exc
                    continue
                except OperationalError as exc:
                    self._uow.rollback()
                    if "locked" in str(exc).lower():
                        raise AppError(
                            "DATABASE_BUSY",
                            "The database is busy; retry the batch",
                            status_code=503,
                        ) from exc
                    raise

                state = self._serialize(study_session)
                return OutcomeBatchResult(
                    **state.model_dump(),
                    accepted=accepted,
                    duplicates=duplicates,
                )

            raise RuntimeError("Outcome write attempts were exhausted")

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
                study_session.status = "finished"
                study_session.finished_at = finished_at
                self._uow.commit()
            return self._summary(study_session)

    def _write_learning_result(
        self,
        study_session: StudySession,
        item: SessionItem,
        outcome: OutcomeWrite,
        *,
        timezone: str,
    ) -> None:
        occurred_at = outcome.occurred_at
        local_date = occurred_at.astimezone(ZoneInfo(timezone)).date()
        snapshot = item.entry_snapshot
        self._uow.study_sessions.add_learning_event(
            LearningEvent(
                client_event_id=str(outcome.client_event_id),
                session_item_id=item.id,
                entry_id=item.entry_id,
                term_key=str(snapshot["normalized_term"]),
                term_snapshot=str(snapshot["term"]),
                vocabulary_snapshot={
                    "id": study_session.vocabulary_id,
                    "name": str(study_session.plan_snapshot["vocabulary_name"]),
                },
                result=outcome.result,
                attempt_count=item.attempt_count,
                client_attempt_count=outcome.attempt_count,
                occurred_at=occurred_at,
                timezone=timezone,
                activity_date=local_date,
            )
        )
        state = self._uow.study_sessions.get_review_state(item.entry_id)
        existing_box = state.box_number if state is not None else None
        box_number, next_review_at = calculate_review_state(
            existing_box,
            outcome.result,
            occurred_at,
        )
        if state is None:
            state = ReviewState(entry_id=item.entry_id)
            self._uow.study_sessions.add_review_state(state)
        state.box_number = box_number
        state.last_reviewed_at = occurred_at
        state.next_review_at = next_review_at

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
    def _deduplicate_batch(
        outcomes: list[OutcomeWrite],
    ) -> list[OutcomeWrite]:
        by_client_id: dict[str, OutcomeWrite] = {}
        by_item_id: dict[str, OutcomeWrite] = {}
        for outcome in outcomes:
            client_event_id = str(outcome.client_event_id)
            previous = by_client_id.get(client_event_id)
            if previous is not None and previous != outcome:
                raise AppError(
                    "IDEMPOTENCY_CONFLICT",
                    "client_event_id was reused with different content",
                    status_code=409,
                    details={"client_event_id": client_event_id},
                )
            item_outcome = by_item_id.get(outcome.session_item_id)
            if item_outcome is not None and item_outcome.client_event_id != (
                outcome.client_event_id
            ):
                raise AppError(
                    "OUTCOME_ALREADY_RECORDED",
                    "The batch contains multiple outcomes for one session item",
                    status_code=409,
                    details={"session_item_id": outcome.session_item_id},
                )
            by_client_id[client_event_id] = outcome
            by_item_id[outcome.session_item_id] = outcome
        return list(by_client_id.values())

    @staticmethod
    def _validate_persisted_outcomes(
        outcomes: list[OutcomeWrite],
        events_by_client_id: dict[str, LearningEvent],
        events_by_item_id: dict[str | None, LearningEvent],
    ) -> None:
        for outcome in outcomes:
            client_event_id = str(outcome.client_event_id)
            existing = events_by_client_id.get(client_event_id)
            if existing is not None and not _event_matches(existing, outcome):
                raise AppError(
                    "IDEMPOTENCY_CONFLICT",
                    "client_event_id was reused with different content",
                    status_code=409,
                    details={"client_event_id": client_event_id},
                )
            item_event = events_by_item_id.get(outcome.session_item_id)
            if item_event is not None and item_event.client_event_id != client_event_id:
                raise AppError(
                    "OUTCOME_ALREADY_RECORDED",
                    "The final result for this item is already recorded",
                    status_code=409,
                    details={"session_item_id": outcome.session_item_id},
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


def calculate_review_state(
    current_box: int | None,
    result: str,
    occurred_at: datetime,
) -> tuple[int, datetime]:
    if current_box is None or result == "again":
        box_number = 0
    else:
        box_number = min(current_box + 1, len(REVIEW_INTERVAL_DAYS) - 1)
    return (
        box_number,
        occurred_at + timedelta(days=REVIEW_INTERVAL_DAYS[box_number]),
    )


def _event_matches(event: LearningEvent, outcome: OutcomeWrite) -> bool:
    return (
        event.session_item_id == outcome.session_item_id
        and event.result == outcome.result
        and event.client_attempt_count == outcome.attempt_count
        and _as_utc(event.occurred_at) == outcome.occurred_at
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
