import random

import pytest
from pydantic import ValidationError

from app.models.vocabulary import Entry
from app.schemas.study_plans import StudyPlanUpdate
from app.services.study_plans import assemble_queue


def entry(entry_id: int, term: str) -> Entry:
    return Entry(
        id=entry_id,
        vocabulary_id=1,
        term=term,
        normalized_term=term.lower(),
        entry_type="word",
        meaning=term,
        tags=[],
    )


def test_queue_with_only_reviews() -> None:
    items = assemble_queue(
        [entry(1, "review-one"), entry(2, "review-two")],
        [],
        daily_review_count=2,
        daily_new_count=2,
        is_random=False,
    )

    assert [(item.entry_id, item.kind) for item in items] == [
        (1, "review"),
        (2, "review"),
    ]


def test_queue_with_only_new_entries() -> None:
    items = assemble_queue(
        [],
        [entry(3, "new-one"), entry(4, "new-two")],
        daily_review_count=2,
        daily_new_count=2,
        is_random=False,
    )

    assert [(item.entry_id, item.kind) for item in items] == [
        (3, "new"),
        (4, "new"),
    ]


def test_queue_places_reviews_before_new_entries() -> None:
    items = assemble_queue(
        [entry(1, "review")],
        [entry(2, "new")],
        daily_review_count=1,
        daily_new_count=1,
        is_random=False,
    )

    assert [item.kind for item in items] == ["review", "new"]


def test_empty_candidates_produce_empty_queue() -> None:
    assert (
        assemble_queue(
            [],
            [],
            daily_review_count=10,
            daily_new_count=10,
            is_random=False,
        )
        == []
    )


def test_randomization_never_crosses_group_boundary() -> None:
    items = assemble_queue(
        [entry(1, "review-one"), entry(2, "review-two")],
        [entry(3, "new-one"), entry(4, "new-two")],
        daily_review_count=2,
        daily_new_count=2,
        is_random=True,
        randomizer=random.Random(7),
    )

    assert [item.kind for item in items] == [
        "review",
        "review",
        "new",
        "new",
    ]
    assert {item.entry_id for item in items[:2]} == {1, 2}
    assert {item.entry_id for item in items[2:]} == {3, 4}


@pytest.mark.parametrize(
    ("daily_review_count", "daily_new_count", "expected_kinds"),
    [
        (0, 2, ["new", "new"]),
        (2, 0, ["review", "review"]),
        (0, 0, []),
    ],
)
def test_zero_limits_are_supported(
    daily_review_count: int,
    daily_new_count: int,
    expected_kinds: list[str],
) -> None:
    items = assemble_queue(
        [entry(1, "review-one"), entry(2, "review-two")],
        [entry(3, "new-one"), entry(4, "new-two")],
        daily_review_count=daily_review_count,
        daily_new_count=daily_new_count,
        is_random=False,
    )

    assert [item.kind for item in items] == expected_kinds


@pytest.mark.parametrize("interval_seconds", [1, 10])
def test_interval_boundaries_are_valid(interval_seconds: int) -> None:
    plan = StudyPlanUpdate(interval_seconds=interval_seconds)

    assert plan.interval_seconds == interval_seconds


@pytest.mark.parametrize("interval_seconds", [0, 11])
def test_interval_outside_boundaries_is_rejected(interval_seconds: int) -> None:
    with pytest.raises(ValidationError):
        StudyPlanUpdate(interval_seconds=interval_seconds)
