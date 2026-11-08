"""残りの工数の推移(要望 128 段階 2)。NiceGUI に依存しない部分。"""

from datetime import date

import pytest

from projectapp.burndown import (
    BurnTask,
    count_workdays,
    next_workday,
    planned_curve,
)
from projectapp.models import Task

ANCHOR = date(2026, 11, 1)  # 日曜。11/02(月)から数える
LAST = date(2026, 11, 8)  # 日曜


def bt(start: date | None, end: date | None, name: str = "x") -> BurnTask:
    return BurnTask(Task(name, id=name), (), start, end)


def test_count_workdays_skips_weekends_and_weekday_holidays() -> None:
    assert count_workdays(date(2026, 11, 2), date(2026, 11, 8), {}) == 5
    assert count_workdays(date(2026, 11, 2), date(2026, 11, 15), {}) == 10
    assert count_workdays(date(2026, 11, 2), date(2026, 11, 8), {date(2026, 11, 4): "祝"}) == 4
    assert count_workdays(date(2026, 11, 2), date(2026, 11, 8), {date(2026, 11, 7): "祝"}) == 5
    assert count_workdays(date(2026, 11, 7), date(2026, 11, 9), {}) == 1
    assert count_workdays(date(2026, 11, 9), date(2026, 11, 8), {}) == 0


def test_next_workday() -> None:
    assert next_workday(date(2026, 11, 2), {}) == date(2026, 11, 2)
    assert next_workday(date(2026, 11, 7), {}) == date(2026, 11, 9)
    assert next_workday(date(2026, 11, 7), {date(2026, 11, 9): "祝"}) == date(2026, 11, 10)


def test_planned_curve_burns_straight_over_the_workdays_of_the_plan() -> None:
    curve = planned_curve([bt(date(2026, 11, 2), date(2026, 11, 4))], [10.0], ANCHOR, LAST, {})
    assert curve == pytest.approx((20 / 3, 10 / 3, 0, 0, 0, 0, 0))


def test_planned_curve_stops_above_zero_when_the_plan_runs_past_the_end() -> None:
    # 金(11/06)〜翌週火(11/10)は稼働日 3 日(金・月・火)。11/06 に 1 日分進み、土日は動かない
    curve = planned_curve([bt(date(2026, 11, 6), date(2026, 11, 10))], [10.0], ANCHOR, LAST, {})
    assert curve == pytest.approx((10, 10, 10, 10, 20 / 3, 20 / 3, 20 / 3))


def test_planned_curve_finishes_an_overdue_task_on_the_next_workday() -> None:
    curve = planned_curve([bt(date(2026, 10, 28), date(2026, 10, 29))], [6.0], ANCHOR, LAST, {})
    assert curve == pytest.approx((0, 0, 0, 0, 0, 0, 0))


def test_planned_curve_from_a_friday_anchor_finishes_on_monday() -> None:
    curve = planned_curve(
        [bt(date(2026, 10, 28), date(2026, 10, 29))], [6.0], date(2026, 11, 6), date(2026, 11, 10), {}
    )
    assert curve == pytest.approx((6, 6, 0, 0))  # 11/07 土・11/08 日・11/09 月で 0


def test_planned_curve_keeps_a_task_whose_plan_is_only_on_days_off() -> None:
    # 土(11/07)〜日(11/08)だけの予定は、次の稼働日(11/09)に終える扱い。期間の中では動かない
    curve = planned_curve([bt(date(2026, 11, 7), date(2026, 11, 8))], [3.0], ANCHOR, LAST, {})
    assert curve == pytest.approx((3, 3, 3, 3, 3, 3, 3))


def test_planned_curve_does_not_move_a_task_without_a_readable_plan() -> None:
    tasks = [bt(None, None, "a"), bt(date(2026, 11, 2), None, "b")]
    assert planned_curve(tasks, [2.0, 3.0], ANCHOR, LAST, {}) == pytest.approx((5,) * 7)


def test_planned_curve_treats_an_end_before_the_start_as_one_day() -> None:
    curve = planned_curve([bt(date(2026, 11, 4), date(2026, 11, 2))], [4.0], ANCHOR, LAST, {})
    assert curve == pytest.approx((4, 4, 0, 0, 0, 0, 0))  # 11/04 の 1 日で終える


def test_planned_curve_does_not_count_a_holiday_as_a_workday() -> None:
    holidays = {date(2026, 11, 3): "祝日"}
    curve = planned_curve([bt(date(2026, 11, 2), date(2026, 11, 4))], [10.0], ANCHOR, LAST, holidays)
    assert curve == pytest.approx((5, 5, 0, 0, 0, 0, 0))


def test_planned_curve_ignores_tasks_without_remaining_work() -> None:
    assert planned_curve([bt(date(2026, 11, 2), date(2026, 11, 4))], [0.0], ANCHOR, LAST, {}) == (0.0,) * 7


def test_planned_curve_is_empty_when_there_are_no_days_after_the_anchor() -> None:
    assert planned_curve([bt(None, None)], [1.0], LAST, LAST, {}) == ()
    assert planned_curve([bt(None, None)], [1.0], date(2026, 11, 9), LAST, {}) == ()
