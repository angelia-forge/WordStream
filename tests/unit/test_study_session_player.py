import pytest

from app.services.study_sessions import (
    move_current_for_retry,
    remaining_milliseconds,
)


@pytest.mark.parametrize(
    ("items", "current_index", "expected", "target"),
    [
        (["a", "b", "c", "d"], 0, ["b", "c", "a", "d"], 2),
        (["a", "b", "c", "d"], 1, ["a", "c", "d", "b"], 3),
        (["a", "b"], 0, ["b", "a"], 1),
        (["a"], 0, ["a"], 0),
    ],
)
def test_retry_plays_after_up_to_two_other_items(
    items: list[str],
    current_index: int,
    expected: list[str],
    target: int,
) -> None:
    assert move_current_for_retry(items, current_index) == target
    assert items == expected


def test_retry_rejects_an_index_outside_the_queue() -> None:
    with pytest.raises(IndexError):
        move_current_for_retry(["a"], 1)


@pytest.mark.parametrize(
    ("deadline", "now", "expected"),
    [
        (8_000.0, 3_000.0, 5_000.0),
        (8_000.0, 8_000.0, 0.0),
        (8_000.0, 9_500.0, 0.0),
    ],
)
def test_remaining_time_uses_an_absolute_deadline(
    deadline: float,
    now: float,
    expected: float,
) -> None:
    assert remaining_milliseconds(deadline, now) == expected
