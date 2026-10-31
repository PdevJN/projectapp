from datetime import date, datetime

import pytest

from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from projectapp.pace import WARNING_RATIO, Pace, pace, warning_pace

NOW = datetime(2026, 10, 7, 12)  # 水曜の昼。稼働の枠は 9:00〜15:30(残り 3.5h)
MON = datetime(2026, 10, 5, 9)


def project_of(*tasks: Task) -> Project:
    return Project("P", base_date=date(2026, 10, 5), members=[Member("田中", 1.0)], sections=[Section("s", list(tasks))])


def judged(task: Task, now: datetime = NOW) -> Pace | None:
    return pace(task, project_of(task), {}, now)


def test_the_warning_ratio_is_one_point_one() -> None:
    assert WARNING_RATIO == 1.10


def test_a_task_on_plan_is_not_a_warning() -> None:
    task = Task("予定どおり", planned_start=MON, effort_hours=19.5, progress=82)
    value = judged(task)
    assert value is not None and value.ratio == pytest.approx(1.0, abs=0.03)
    assert not value.warning
    assert warning_pace(task, project_of(task), {}, NOW) is None


def test_a_task_behind_plan_is_a_warning() -> None:
    task = Task("遅れ気味", planned_start=MON, effort_hours=19.5, progress=50)
    value = warning_pace(task, project_of(task), {}, NOW)
    assert value is not None
    assert value.remaining == pytest.approx(9.75)
    assert value.capacity == pytest.approx(3.5)
    assert value.ratio == pytest.approx(2.786, abs=0.001)


def test_the_boundary_is_one_point_one() -> None:
    inside = Task("a", planned_start=MON, effort_hours=19.5, progress=81)
    over = Task("b", planned_start=MON, effort_hours=19.5, progress=80)
    assert not judged(inside).warning  # type: ignore[union-attr]
    assert judged(over).warning  # type: ignore[union-attr]


def test_a_manual_end_with_room_is_not_a_warning() -> None:
    task = Task(
        "余裕あり", planned_start=MON, effort_hours=19.5, progress=50,
        planned_end=datetime(2026, 10, 9, 15, 30), planned_end_manual=True,
    )
    value = judged(task)
    assert value is not None and not value.warning


def test_a_plan_too_short_for_the_effort_warns_before_the_start() -> None:
    task = Task(
        "足りない計画", planned_start=MON, effort_hours=40,
        planned_end=datetime(2026, 10, 6, 15, 30), planned_end_manual=True,
    )
    value = judged(task, now=datetime(2026, 10, 5, 8))
    assert value is not None and value.warning and value.ratio == pytest.approx(40 / 13)


def test_a_task_not_started_after_its_start_is_a_warning() -> None:
    task = Task("着手が遅れた", planned_start=MON, effort_hours=19.5)
    assert warning_pace(task, project_of(task), {}, NOW) is not None


def test_a_task_before_its_start_follows_the_plan() -> None:
    task = Task("まだ先", planned_start=datetime(2026, 10, 8, 9), effort_hours=6.5)
    value = judged(task)
    assert value is not None and value.ratio == pytest.approx(1.0) and not value.warning


def test_no_capacity_with_work_left_is_a_warning() -> None:
    task = Task(
        "枠がない", planned_start=datetime(2026, 10, 9, 15, 30), effort_hours=1,
        planned_end=datetime(2026, 10, 10, 10), planned_end_manual=True,
    )
    value = judged(task, now=datetime(2026, 10, 9, 16))
    assert value is not None and value.capacity == 0 and value.ratio == float("inf") and value.warning


def test_overdue_tasks_are_left_to_the_red_row() -> None:
    late_end = Task("完了予定を過ぎた", planned_start=MON, effort_hours=6.5)
    late_deadline = Task("締切を過ぎた", planned_start=NOW, effort_hours=6.5, deadline=datetime(2026, 10, 7, 10))
    assert judged(late_end) is None
    assert judged(late_deadline) is None


@pytest.mark.parametrize(
    "task",
    [
        Task("終了", planned_start=MON, effort_hours=19.5, status=Status.DONE),
        Task("工数なし", planned_start=MON, planned_end=datetime(2026, 10, 9, 15, 30)),
        Task("日程なし", effort_hours=10),
        Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9, 17)),
        Task("残りなし", planned_start=MON, effort_hours=19.5, progress=100),
    ],
)
def test_tasks_that_cannot_be_judged_give_none(task: Task) -> None:
    assert judged(task) is None


def test_the_hint_names_the_numbers() -> None:
    assert Pace(9.75, 3.5).hint() == "警告: 残り 9.8h / 稼働 3.5h(279%)"
    assert Pace(1.0, 0.0).hint() == "警告: 残り 1.0h / 稼働 0.0h"


def test_assignees_change_the_capacity() -> None:
    task = Task("二人分", planned_start=MON, effort_hours=19.5, progress=50, assignees=[Assignee("田中", 1.0)])
    value = judged(task)
    assert value is not None and value.capacity == pytest.approx(3.5)
