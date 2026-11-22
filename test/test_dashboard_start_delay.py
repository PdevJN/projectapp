"""ダッシュボードの`進捗と遅れ`の着工遅れ(要望 161 段階 2)。今は 2026-10-07(水)12:00。"""

from datetime import date, datetime

from projectapp.dashboard import StartDelayRow, summarize_progress
from projectapp.models import (
    Actual,
    Assignee,
    Member,
    Project,
    Status,
    Task,
)
from projectapp.start_delay import DelayKind

NOW = datetime(2026, 10, 7, 12)
MON = datetime(2026, 10, 5, 9)  # 月曜


def project_of(*tasks: Task, **settings: object) -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=list(tasks),
        **settings,
    )


def task(
    name: str,
    *actuals: Actual,
    status: Status = Status.NOT_STARTED,
    who: str = "田中",
    start: datetime = MON,
) -> Task:
    return Task(
        name,
        planned_start=start,
        planned_end=datetime(2026, 10, 9, 17),
        effort_hours=16,
        status=status,
        actuals=list(actuals),
        assignees=[Assignee(who)],
    )


def rows(project: Project, member: str | None = None) -> list[StartDelayRow]:
    return summarize_progress(project, {}, NOW, member).start_delays


def test_an_unstarted_task_past_its_start_is_counted() -> None:
    assert rows(project_of(task("a"))) == [
        StartDelayRow("a", DelayKind.UNSTARTED, 2, ("田中",))
    ]


def test_a_task_left_paused_is_counted_as_a_stop() -> None:
    paused = task(
        "p",
        Actual(MON, datetime(2026, 10, 5, 12)),
        status=Status.PAUSED,
    )
    assert rows(project_of(paused)) == [
        StartDelayRow("p", DelayKind.STOP, 1, ("田中",))
    ]


def test_past_delays_are_not_counted() -> None:
    late_start = task(
        "late",
        Actual(datetime(2026, 10, 6, 9), None),  # 火曜に着手(予定は月曜)。今は進行中
        status=Status.RUNNING,
    )
    resumed = task(
        "resumed",
        Actual(MON, datetime(2026, 10, 5, 12)),
        Actual(datetime(2026, 10, 7, 9), None),  # 火曜が抜けたが、再開している
        status=Status.RUNNING,
    )
    assert rows(project_of(late_start, resumed)) == []


def test_the_grace_days_apply() -> None:
    assert rows(project_of(task("a"), start_delay_grace=2)) == []
    assert len(rows(project_of(task("a"), start_delay_grace=1))) == 1


def test_nothing_is_counted_when_the_setting_is_off() -> None:
    project = project_of(task("a"), start_delay_enabled=False)
    progress = summarize_progress(project, {}, NOW)
    assert progress.start_delays == []
    assert progress.start_delay_enabled is False


def test_the_setting_is_reported_when_on() -> None:
    assert (
        summarize_progress(project_of(task("a")), {}, NOW).start_delay_enabled is True
    )


def test_the_member_filter_applies() -> None:
    project = project_of(task("a", who="田中"), task("b", who="鈴木"))
    assert [r.name for r in rows(project, "鈴木")] == ["b"]


def test_rows_are_sorted_by_days_descending() -> None:
    old = task("old", start=datetime(2026, 10, 1, 9))  # 木曜から。木・金・月・火 = 4 日
    new = task("new")  # 月曜から 2 日
    assert [(r.name, r.days) for r in rows(project_of(new, old))] == [
        ("old", 4),
        ("new", 2),
    ]


def test_a_done_task_is_not_counted() -> None:
    done = task("d", Actual(MON, datetime(2026, 10, 5, 12)), status=Status.DONE)
    assert rows(project_of(done)) == []
