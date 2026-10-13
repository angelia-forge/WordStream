from datetime import UTC, date, datetime

from app.services.statistics import calculate_streak, local_date_at


def test_streak_includes_today_when_today_has_activity() -> None:
    activity_dates = [
        date(2026, 10, 12),
        date(2026, 10, 11),
        date(2026, 10, 10),
        date(2026, 10, 8),
    ]

    assert calculate_streak(activity_dates, date(2026, 10, 12)) == 3


def test_streak_allows_today_to_be_unfinished() -> None:
    activity_dates = [
        date(2026, 10, 11),
        date(2026, 10, 10),
        date(2026, 10, 9),
    ]

    assert calculate_streak(activity_dates, date(2026, 10, 12)) == 3


def test_streak_is_zero_after_a_gap() -> None:
    assert calculate_streak([date(2026, 10, 10)], date(2026, 10, 12)) == 0


def test_local_date_changes_at_local_midnight() -> None:
    assert local_date_at(
        datetime(2026, 10, 12, 15, 59, tzinfo=UTC),
        "Asia/Shanghai",
    ) == date(2026, 10, 12)
    assert local_date_at(
        datetime(2026, 10, 12, 16, 0, tzinfo=UTC),
        "Asia/Shanghai",
    ) == date(2026, 10, 13)


def test_local_date_handles_new_york_daylight_saving_boundaries() -> None:
    assert local_date_at(
        datetime(2026, 3, 8, 4, 59, tzinfo=UTC),
        "America/New_York",
    ) == date(2026, 3, 7)
    assert local_date_at(
        datetime(2026, 3, 8, 5, 0, tzinfo=UTC),
        "America/New_York",
    ) == date(2026, 3, 8)
    assert local_date_at(
        datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        "America/New_York",
    ) == date(2026, 11, 1)
