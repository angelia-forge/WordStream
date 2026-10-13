from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime

from app.exceptions import AppError
from app.models.learning import StudyPlan
from app.models.setting import utc_now
from app.models.vocabulary import Entry
from app.schemas.study_plans import (
    StudyPlanRead,
    StudyPlanUpdate,
    StudyQueue,
    StudyQueueItem,
)
from app.unit_of_work import AbstractUnitOfWork


class StudyPlanService:
    def __init__(self, uow: AbstractUnitOfWork) -> None:
        self._uow = uow

    def get_plan(self, vocabulary_id: int) -> StudyPlanRead:
        plan = self.find_plan(vocabulary_id)
        if plan is None:
            raise AppError(
                "PLAN_NOT_FOUND",
                "Study plan was not found",
                status_code=404,
            )
        return plan

    def find_plan(self, vocabulary_id: int) -> StudyPlanRead | None:
        with self._uow:
            self._require_vocabulary(vocabulary_id)
            plan = self._uow.study.get_plan(vocabulary_id)
            if plan is None:
                return None
            return StudyPlanRead.model_validate(plan)

    def upsert_plan(
        self,
        vocabulary_id: int,
        update: StudyPlanUpdate,
    ) -> StudyPlanRead:
        with self._uow:
            self._require_vocabulary(vocabulary_id)
            plan = self._uow.study.get_plan(vocabulary_id)
            values = update.model_dump()
            if plan is None:
                plan = StudyPlan(vocabulary_id=vocabulary_id, **values)
                self._uow.study.add_plan(plan)
            else:
                for field, value in values.items():
                    setattr(plan, field, value)
                plan.updated_at = utc_now()
            self._uow.commit()
            return StudyPlanRead.model_validate(plan)

    def build_queue(
        self,
        vocabulary_id: int,
        *,
        now: datetime | None = None,
        randomizer: random.Random | None = None,
    ) -> StudyQueue:
        with self._uow:
            self._require_vocabulary(vocabulary_id)
            plan = self._uow.study.get_plan(vocabulary_id)
            if plan is None:
                raise AppError(
                    "PLAN_NOT_FOUND",
                    "Study plan was not found",
                    status_code=404,
                )
            due_reviews = self._uow.study.list_due_reviews(
                vocabulary_id,
                now=now or utc_now(),
            )
            new_entries = self._uow.study.list_new_entries(vocabulary_id)
            items = assemble_queue(
                due_reviews,
                new_entries,
                daily_review_count=plan.daily_review_count,
                daily_new_count=plan.daily_new_count,
                is_random=plan.is_random,
                randomizer=randomizer,
            )
            return StudyQueue(
                vocabulary_id=vocabulary_id,
                interval_seconds=plan.interval_seconds,
                is_loop=plan.is_loop,
                items=items,
            )

    def _require_vocabulary(self, vocabulary_id: int) -> None:
        if self._uow.vocabularies.get(vocabulary_id) is None:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Vocabulary was not found",
                status_code=404,
            )


def assemble_queue(
    due_reviews: Sequence[Entry],
    new_entries: Sequence[Entry],
    *,
    daily_review_count: int,
    daily_new_count: int,
    is_random: bool,
    randomizer: random.Random | None = None,
) -> list[StudyQueueItem]:
    reviews = list(due_reviews)
    new = list(new_entries)
    if is_random:
        source = randomizer or random.SystemRandom()
        source.shuffle(reviews)
        source.shuffle(new)

    review_items = [
        StudyQueueItem(entry_id=entry.id, term=entry.term, kind="review")
        for entry in reviews[:daily_review_count]
    ]
    new_items = [
        StudyQueueItem(entry_id=entry.id, term=entry.term, kind="new")
        for entry in new[:daily_new_count]
    ]
    return review_items + new_items
