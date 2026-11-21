"""Shift + Enter の小さなダイアログ(名前・工数・開始日・締切日)の入力を、タスクの値にする。"""

from datetime import date, datetime, time

import pytest

from projectapp.effortunits import EffortUnit
from projectapp.forms import build_detailed_task
from projectapp.models import Task

TODAY = date(2026, 11, 20)
WORK_START = time(9, 0)


def build(
    name: str = "新規",
    effort: float | None = None,
    unit: EffortUnit = EffortUnit.HOURS,
    start: str = "",
    deadline: str = "",
) -> Task:
    return build_detailed_task(
        name,
        effort,
        unit,
        start,
        deadline,
        today=TODAY,
        daily_hours=6.0,
        work_start=WORK_START,
    )


def test_blank_details_give_the_same_task_as_a_name_only_task() -> None:
    task = build()
    assert (task.name, task.effort_hours, task.planned_start, task.deadline) == (
        "新規",
        0.0,
        None,
        None,
    )


def test_effort_start_and_deadline_are_set() -> None:
    task = build(effort=8, start="2026-11-24", deadline="2026-11-30")
    assert task.effort_hours == 8
    assert task.planned_start == datetime(2026, 11, 24, 9, 0)
    assert task.deadline is not None and task.deadline.date() == date(2026, 11, 30)


@pytest.mark.parametrize(
    ("unit", "hours"),
    [
        (EffortUnit.HOURS, 2),
        (EffortUnit.DAYS, 12),
        (EffortUnit.WEEKS, 60),
        (EffortUnit.MONTHS, 240),
    ],
)
def test_effort_is_converted_to_hours_by_the_unit(
    unit: EffortUnit, hours: float
) -> None:
    assert build(effort=2, unit=unit).effort_hours == hours


def test_short_dates_are_read_like_the_other_date_fields() -> None:
    assert build(start="11/24").planned_start == datetime(2026, 11, 24, 9, 0)


def test_the_same_day_is_allowed_for_start_and_deadline() -> None:
    task = build(start="2026-11-24", deadline="2026-11-24")
    assert task.planned_start is not None and task.deadline is not None
    assert task.planned_start < task.deadline


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": ""}, "名前"),
        ({"start": "あした"}, "開始日"),
        ({"deadline": "2026-02-30"}, "締切日"),
        ({"effort": -1}, "工数"),
        ({"effort": float("nan")}, "工数"),
        ({"start": "2026-12-01", "deadline": "2026-11-30"}, "締切日は開始日以降"),
    ],
)
def test_invalid_details_are_rejected_with_a_message(
    kwargs: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build(**kwargs)
