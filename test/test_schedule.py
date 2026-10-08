from datetime import date, datetime

from projectapp.models import Assignee, Actual, Member, Project, Status, Task
from projectapp.timeline import (
    Schedule,
    counted_span,
    effective_end,
    effective_start,
    is_overdue,
    overallocations,
    visible_range,
)

HOLIDAYS: dict[date, str] = {}
MON = datetime(2026, 10, 5, 9, 0)  # 月曜 9:00


def task(name: str, *predecessors: str, **fields: object) -> Task:
    return Task(name, id=name, predecessors=list(predecessors), **fields)  # type: ignore[arg-type]


def project(*tasks: Task) -> Project:
    return Project("p", tasks=list(tasks), daily_hours=6.5)


def start_of(proj: Project, name: str) -> datetime | None:
    found = next(t for t in proj.all_tasks() if t.name == name)
    return effective_start(found, proj, HOLIDAYS)


def end_of(proj: Project, name: str) -> datetime | None:
    found = next(t for t in proj.all_tasks() if t.name == name)
    return effective_end(found, proj, HOLIDAYS)


def test_no_predecessors_keeps_the_planned_start() -> None:
    proj = project(task("a", planned_start=MON, effort_hours=6.5))
    assert start_of(proj, "a") == MON
    assert end_of(proj, "a") == datetime(2026, 10, 5, 15, 30)


def test_a_late_predecessor_pushes_the_start() -> None:
    a = task("a", planned_start=MON, effort_hours=13)  # 月 9:00 → 火 15:30
    b = task("b", "a", planned_start=MON, effort_hours=6.5)
    proj = project(a, b)
    assert start_of(proj, "b") == datetime(2026, 10, 6, 15, 30)
    assert end_of(proj, "b") == datetime(2026, 10, 7, 15, 30)  # 火 15:30 は枠の終わり → 水


def test_an_early_predecessor_does_not_pull_the_start_back() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_start=datetime(2026, 10, 8, 9, 0), effort_hours=1)
    assert start_of(project(a, b), "b") == datetime(2026, 10, 8, 9, 0)


def test_the_latest_of_several_predecessors_wins() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    c = task("c", planned_start=MON, effort_hours=13)
    b = task("b", "a", "c", planned_start=MON, effort_hours=1)
    assert start_of(project(a, c, b), "b") == datetime(2026, 10, 6, 15, 30)


def test_a_chain_is_resolved() -> None:
    a = task("a", planned_start=MON, effort_hours=6.5)  # 月 15:30 まで
    b = task("b", "a", planned_start=MON, effort_hours=6.5)
    c = task("c", "b", planned_start=MON, effort_hours=1)
    proj = project(a, b, c)
    assert start_of(proj, "b") == datetime(2026, 10, 5, 15, 30)
    assert start_of(proj, "c") == end_of(proj, "b")


def test_no_planned_start_uses_the_predecessors_finish() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", effort_hours=1)
    proj = project(a, b)
    assert start_of(proj, "b") == datetime(2026, 10, 5, 10, 0)
    assert end_of(proj, "b") == datetime(2026, 10, 5, 11, 0)


def test_no_predecessor_finish_and_no_start_stays_empty() -> None:
    a = task("a")  # 開始予定も締切もなく、完了予定が求まらない
    b = task("b", "a")
    assert start_of(project(a, b), "b") is None


def test_a_predecessor_without_an_end_is_ignored() -> None:
    a = task("a")
    c = task("c", planned_start=MON, effort_hours=1)
    b = task("b", "a", "c", planned_start=MON, effort_hours=1)
    assert start_of(project(a, c, b), "b") == datetime(2026, 10, 5, 10, 0)


def test_a_finished_predecessor_uses_its_actual_end() -> None:
    a = task(
        "a",
        planned_start=MON,
        effort_hours=1,
        status=Status.DONE,
        actuals=[Actual(MON, datetime(2026, 10, 7, 12, 0))],
    )
    b = task("b", "a", planned_start=MON, effort_hours=1)
    assert start_of(project(a, b), "b") == datetime(2026, 10, 7, 12, 0)


def test_a_finished_predecessor_without_actuals_uses_the_planned_end() -> None:
    a = task("a", planned_start=MON, effort_hours=1, status=Status.DONE)
    b = task("b", "a", planned_start=MON, effort_hours=1)
    assert start_of(project(a, b), "b") == datetime(2026, 10, 5, 10, 0)


def test_a_manual_end_shifts_by_the_pushed_amount() -> None:
    a = task("a", planned_start=MON, effort_hours=13)  # 火 15:30 まで
    b = task(
        "b",
        "a",
        planned_start=MON,
        planned_end=datetime(2026, 10, 5, 18, 0),
        planned_end_manual=True,
        effort_hours=4,
    )
    shift = datetime(2026, 10, 6, 15, 30) - MON
    assert end_of(project(a, b), "b") == datetime(2026, 10, 5, 18, 0) + shift


def test_a_planned_end_without_effort_shifts_by_the_pushed_amount() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, planned_end=datetime(2026, 10, 5, 18, 0))
    shift = datetime(2026, 10, 6, 15, 30) - MON
    assert end_of(project(a, b), "b") == datetime(2026, 10, 5, 18, 0) + shift


def test_a_manual_end_without_a_planned_start_is_not_shifted() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_end=datetime(2026, 10, 9, 18, 0))
    assert end_of(project(a, b), "b") == datetime(2026, 10, 9, 18, 0)


def test_the_deadline_never_moves() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, effort_hours=1, deadline=datetime(2026, 10, 6, 12, 0))
    proj = project(a, b)
    found = proj.tasks[1]
    assert found.deadline == datetime(2026, 10, 6, 12, 0)
    end = end_of(proj, "b")
    assert end is not None and end > found.deadline  # 押し出されて、完了予定が締切を過ぎる
    assert not is_overdue(found, proj, HOLIDAYS, datetime(2026, 10, 1))  # 超過は現在時刻と比べる(既存)
    assert is_overdue(found, proj, HOLIDAYS, datetime(2026, 10, 6, 13, 0))


def test_a_cycle_does_not_recurse_forever() -> None:
    a = task("a", "b", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_start=MON, effort_hours=1)
    proj = project(a, b)
    assert start_of(proj, "a") is not None
    assert start_of(proj, "b") is not None


def test_a_missing_predecessor_is_ignored() -> None:
    b = task("b", "zz", planned_start=MON, effort_hours=1)
    assert start_of(project(b), "b") == MON


def test_a_schedule_matches_the_single_task_calls() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, effort_hours=2)
    c = task("c", "b", planned_start=MON, effort_hours=2)
    proj = project(a, b, c)
    schedule = Schedule(proj, HOLIDAYS)
    for t in proj.all_tasks():
        assert schedule.start(t) == effective_start(t, proj, HOLIDAYS)
        assert schedule.end(t) == effective_end(t, proj, HOLIDAYS)
        assert effective_end(t, proj, HOLIDAYS, schedule) == schedule.end(t)


def test_latest_finish_is_none_without_predecessors() -> None:
    a = task("a", planned_start=MON, effort_hours=1)
    b = task("b", "a", planned_start=MON, effort_hours=1)
    schedule = Schedule(project(a, b), HOLIDAYS)
    assert schedule.latest_finish(a) is None
    assert schedule.latest_finish(b) == datetime(2026, 10, 5, 10, 0)


def test_counted_span_and_overallocations_use_the_pushed_start() -> None:
    a = task("a", planned_start=MON, effort_hours=13)
    b = task("b", "a", planned_start=MON, effort_hours=2, assignees=[Assignee("x")])
    c = task("c", planned_start=datetime(2026, 10, 6, 15, 30), effort_hours=2, assignees=[Assignee("x")])
    proj = Project("p", tasks=[a, b, c], members=[Member("x")])
    span = counted_span(b, proj, HOLIDAYS)
    assert span is not None and span[0] == datetime(2026, 10, 6, 15, 30)
    assert overallocations(proj, HOLIDAYS)  # b と c が、押し出された b の期間で重なる


def test_visible_range_includes_the_pushed_end() -> None:
    a = task("a", planned_start=MON, effort_hours=65)  # 10 稼働日
    b = task("b", "a", planned_start=MON, effort_hours=1)
    _, end = visible_range(project(a, b), HOLIDAYS)
    assert end >= date(2026, 10, 20)
