from datetime import date, time

import pytest

from projectapp.models import Project, WorkDay
from projectapp.workdays import sort_work_days, validate_work_days, work_day_map


def test_work_day_defaults_to_a_rest_day_marker_of_none() -> None:
    rest = WorkDay(date(2026, 10, 12))
    assert rest.start is None and rest.end is None
    assert Project("p").work_days == []


def test_validate_accepts_windows_and_rests() -> None:
    validate_work_days([WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 12))])


@pytest.mark.parametrize(
    "days",
    [
        [WorkDay(date(2026, 10, 17), time(13), time(13))],  # 開始 = 終了
        [WorkDay(date(2026, 10, 17), time(16), time(13))],  # 開始 > 終了
        [WorkDay(date(2026, 10, 17), time(13), None)],  # 片方だけ
        [WorkDay(date(2026, 10, 17), None, time(16))],
        [WorkDay(date(2026, 10, 17), time(9), time(10)), WorkDay(date(2026, 10, 17))],  # 日付の重複
        [WorkDay(date(1999, 12, 31), time(9), time(10))],  # 年の範囲外
        [WorkDay(date(2101, 1, 1))],
    ],
)
def test_validate_rejects_bad_rows(days: list[WorkDay]) -> None:
    with pytest.raises(ValueError):
        validate_work_days(days)


def test_sort_and_map() -> None:
    a, b = WorkDay(date(2026, 10, 18), time(9), time(10)), WorkDay(date(2026, 10, 12))
    assert sort_work_days([a, b]) == [b, a]
    assert work_day_map([a, b]) == {date(2026, 10, 18): a, date(2026, 10, 12): b}
