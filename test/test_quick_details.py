"""Shift + Enter の小さなダイアログ(名前・工数・開始日・締切日)の入力を、タスクの値にする。"""

from datetime import date, datetime, time

import pytest

from projectapp.effortunits import EffortUnit
from projectapp.forms import build_detailed_task

TODAY = date(2026, 11, 20)
WORK_START = time(9, 0)


def build(**kwargs: object):
    values: dict[str, object] = {
        "name": "新規",
        "effort": None,
        "unit": EffortUnit.HOURS,
        "start": "",
        "deadline": "",
    }
    values.update(kwargs)
    return build_detailed_task(
        values["name"],  # ty: ignore[invalid-argument-type]
        values["effort"],  # ty: ignore[invalid-argument-type]
        values["unit"],  # ty: ignore[invalid-argument-type]
        values["start"],  # ty: ignore[invalid-argument-type]
        values["deadline"],  # ty: ignore[invalid-argument-type]
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


def test_effort_is_converted_from_days_to_hours() -> None:
    assert build(effort=2, unit=EffortUnit.DAYS).effort_hours == 12


def test_short_dates_are_read_like_the_other_date_fields() -> None:
    assert build(start="11/24").planned_start == datetime(2026, 11, 24, 9, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"start": "あした"},
        {"deadline": "2026-02-30"},
        {"effort": -1},
        {"start": "2026-12-01", "deadline": "2026-11-30"},
    ],
)
def test_invalid_details_are_rejected_with_a_message(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        build(**kwargs)
