from datetime import date

from app.services.statistics import calculate_streak


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
