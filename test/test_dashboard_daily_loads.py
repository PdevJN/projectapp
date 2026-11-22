from datetime import date, datetime

from projectapp.dashboard import Period, daily_loads, summarize_loads
from projectapp.models import Assignee, Member, Project, Status, Task, WorkDay

WEEK = Period(date(2026, 11, 16), date(2026, 11, 22))  # 月〜日


def task(
    task_id: str, *assignees: Assignee, status: Status = Status.NOT_STARTED
) -> Task:
    return Task(
        task_id,
        id=task_id,
        planned_start=datetime(2026, 11, 16, 9),
        planned_end=datetime(2026, 11, 20, 17),
        effort_hours=40,
        assignees=list(assignees),
        status=status,
    )


def project(*tasks: Task, members: list[Member] | None = None) -> Project:
    return Project(
        "p",
        base_date=date(2026, 11, 16),
        members=members or [Member("田中", 1.0), Member("鈴木", 1.0)],
        tasks=list(tasks),
    )


def values(loads: dict[str, list[tuple[date, float]]], name: str) -> list[float]:
    return [round(total, 2) for _, total in loads[name]]


def test_a_single_task_loads_each_workday_of_the_assignee() -> None:
    loads = daily_loads(project(task("a", Assignee("田中"))), {}, WEEK)
    assert [day for day, _ in loads["田中"]] == [
        date(2026, 11, d) for d in range(16, 21)
    ]
    assert values(loads, "田中") == [1.0] * 5
    assert values(loads, "鈴木") == [0.0] * 5


def test_overlapping_tasks_add_up_and_exceed_100_percent() -> None:
    both = project(task("a", Assignee("田中")), task("b", Assignee("田中", 0.5)))
    assert max(values(daily_loads(both, {}, WEEK), "田中")) > 1.0


def test_finished_tasks_are_not_counted() -> None:
    done = project(task("a", Assignee("田中"), status=Status.DONE))
    assert values(daily_loads(done, {}, WEEK), "田中") == [0.0] * 5


def test_a_day_off_is_left_out_of_the_workdays() -> None:
    off = Member("田中", 1.0, work_days=[WorkDay(date(2026, 11, 18))])
    loads = daily_loads(project(task("a", Assignee("田中")), members=[off]), {}, WEEK)
    assert date(2026, 11, 18) not in {day for day, _ in loads["田中"]}
    assert len(loads["田中"]) == 4


def test_a_period_without_workdays_gives_an_empty_list() -> None:
    weekend = Period(date(2026, 11, 21), date(2026, 11, 22))
    loads = daily_loads(project(task("a", Assignee("田中"))), {}, weekend)
    assert loads["田中"] == []


def test_the_member_scope_limits_the_result() -> None:
    loads = daily_loads(project(task("a", Assignee("田中"))), {}, WEEK, "田中")
    assert list(loads) == ["田中"]
    assert daily_loads(project(), {}, WEEK, frozenset({"いない人"})) == {}


def test_it_agrees_with_summarize_loads() -> None:
    both = project(task("a", Assignee("田中")), task("b", Assignee("田中", 0.5)))
    totals = [total for _, total in daily_loads(both, {}, WEEK)["田中"]]
    stats = summarize_loads(both, WEEK, {})["田中"]
    assert round(sum(totals) / len(totals), 6) == round(stats.average, 6)
    assert round(max(totals), 6) == round(stats.peak, 6)
    assert sum(1 for t in totals if t > 1.0 + 1e-9) == stats.overload_days
