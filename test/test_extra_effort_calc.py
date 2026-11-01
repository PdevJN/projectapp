from datetime import date, datetime

import pytest

from projectapp.decompose import decompose, default_parts
from projectapp.models import (
    Assignee,
    ExtraEffort,
    Member,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.remaining import remaining_hours, total_effort
from projectapp.timeline import Schedule

MON = datetime(2026, 10, 5, 9)  # 月曜 9:00。稼働の枠は 9:00〜15:30(6.5h)
EXTRA = [ExtraEffort(date(2026, 10, 6), 6.5, "見つかった作業")]


def project_of(task: Task) -> Project:
    return Project(
        "P", base_date=date(2026, 10, 5), members=[Member("田中", 1.0)], tasks=[task]
    )


def task_with(extra: list[ExtraEffort] | None = None, **kw: object) -> Task:
    return Task(
        "a",
        id="t1",
        planned_start=MON,
        effort_hours=13.0,
        assignees=[Assignee("田中", 1.0)],
        extra_efforts=list(extra or []),
        **kw,  # type: ignore[arg-type]
    )


def test_total_effort_adds_the_extra_efforts() -> None:
    task = task_with(EXTRA)
    assert task.total_effort == 19.5
    assert total_effort(task) == 19.5


def test_the_computed_end_moves_by_the_extra_effort() -> None:
    plain, extended = task_with(), task_with(EXTRA)
    end_plain = Schedule(project_of(plain), {}).end(plain)
    end_extended = Schedule(project_of(extended), {}).end(extended)
    assert end_plain == datetime(2026, 10, 6, 15, 30)
    assert end_extended == datetime(2026, 10, 7, 15, 30)


def test_a_manual_end_does_not_move() -> None:
    manual = dict(planned_end=datetime(2026, 10, 9, 17), planned_end_manual=True)
    plain, extended = task_with(**manual), task_with(EXTRA, **manual)
    end_plain = Schedule(project_of(plain), {}).end(plain)
    end_extended = Schedule(project_of(extended), {}).end(extended)
    assert end_plain == end_extended == datetime(2026, 10, 9, 17)


def test_the_remaining_hours_count_the_extra_effort_with_the_progress_kept() -> None:
    now = datetime(2026, 10, 7, 12)
    plain = task_with(status=Status.RUNNING, progress=50)
    extended = task_with(EXTRA, status=Status.RUNNING, progress=50)
    assert remaining_hours(plain, project_of(plain), {}, now) == pytest.approx(6.5)
    assert remaining_hours(extended, project_of(extended), {}, now) == pytest.approx(
        9.75
    )


def test_decomposing_splits_the_total_and_leaves_no_history_on_the_summary() -> None:
    task = task_with(EXTRA)  # 合計 19.5h
    project = Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        sections=[Section("S", tasks=[task])],
    )
    parts = default_parts(task, 2)
    assert sum(part.effort_hours for part in parts) == pytest.approx(19.5)
    children = decompose(project, (0,), 0, parts, holidays={}, today=MON)
    summary = project.sections[0].tasks[0]
    assert summary.kind is TaskKind.SUMMARY and summary.extra_efforts == []
    assert sum(child.effort_hours for child in children) == pytest.approx(19.5)
    assert all(child.extra_efforts == [] for child in children)
