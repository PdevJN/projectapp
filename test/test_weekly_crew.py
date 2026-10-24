from datetime import date, datetime, time

import pytest

from projectapp.models import Assignee, Member, Project, Task, union_assignees
from projectapp.timeline import (
    Worker,
    calc_end,
    consumed_slices,
    crew_on,
    effective_end,
    week_index,
    weekly_crews,
)

OPEN = time(9, 0)
WED = datetime(2026, 10, 7, 9, 0)  # 水曜 9:00
MON = datetime(2026, 10, 5, 9, 0)
HOLIDAYS: dict[date, str] = {}


def workers(*rates: float) -> list[Worker]:
    return [Worker(rate) for rate in rates]


def people() -> list[Member]:
    return [Member("田中", 1.0), Member("鈴木", 1.0)]


def weekly_task(name: str, weeks: list[list[Assignee]], **kwargs: object) -> Task:
    return Task(name, id=name, assignees=union_assignees(weeks), weekly_crew=weeks, **kwargs)  # type: ignore[arg-type]


def project_of(*tasks: Task) -> Project:
    return Project("p", members=people(), tasks=list(tasks), daily_hours=6.5)


@pytest.mark.parametrize(
    ("day", "count", "expected"),
    [
        (date(2026, 10, 7), 3, 0),
        (date(2026, 10, 13), 3, 0),  # 6 日目
        (date(2026, 10, 14), 3, 1),  # 7 日目の次
        (date(2026, 10, 21), 3, 2),
        (date(2026, 11, 30), 3, 2),  # 最後の週より後は最後の週
        (date(2026, 10, 1), 3, 0),  # 開始より前は第1週
        (date(2026, 10, 20), 1, 0),
    ],
)
def test_week_index_counts_seven_calendar_days_from_the_start(day: date, count: int, expected: int) -> None:
    assert week_index(date(2026, 10, 7), day, count) == expected


def test_crew_on_picks_the_week_and_falls_back_to_the_assignees() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    weekly = weekly_task("w", [[a], [a, b]])
    assert crew_on(weekly, date(2026, 10, 7), date(2026, 10, 8)) == [a]
    assert crew_on(weekly, date(2026, 10, 7), date(2026, 10, 15)) == [a, b]
    plain = Task("p", assignees=[b])
    assert crew_on(plain, date(2026, 10, 7), date(2026, 10, 15)) == [b]


def test_the_second_week_runs_faster() -> None:
    # 第1週(水〜火の稼働日 5 日 = 32.5h)は 1 人。残り 7.5h を第2週の 2 人で 3.75h
    end = calc_end(WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)])
    assert end == datetime(2026, 10, 14, 12, 45)


def test_the_last_week_continues() -> None:
    end = calc_end(WED, 100.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)])
    assert end == datetime(2026, 10, 21, 10, 15)  # 第2週は 65h、残り 2.5h を同じ 2 人で 1.25h


def test_the_example_of_five_weeks() -> None:
    weeks = [workers(1.0), workers(1.0, 1.0), workers(1.0, 1.0), workers(1.0, 1.0, 1.0), workers(1.0)]
    assert calc_end(MON, 100.0, 6.5, OPEN, HOLIDAYS, weeks=weeks) == datetime(2026, 10, 19, 10, 15)


def test_one_week_is_the_same_as_a_plain_crew() -> None:
    plain = calc_end(WED, 9.0, 6.5, OPEN, HOLIDAYS, [Worker(1.5)])
    assert calc_end(WED, 9.0, 6.5, OPEN, HOLIDAYS, weeks=[[Worker(1.5)]]) == plain


def test_a_week_without_workers_runs_as_one_person() -> None:
    assert calc_end(WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[[], workers(1.0, 1.0)]) == calc_end(
        WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)]
    )


def test_invalid_effort_still_gives_none_with_weeks() -> None:
    assert calc_end(WED, 0.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0)]) is None
    assert calc_end(WED, float("inf"), 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0)]) is None


def test_the_schedule_uses_the_weekly_crew_of_the_task() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    task = weekly_task("a", [[a], [a, b]], planned_start=WED, effort_hours=40.0)
    assert effective_end(task, project_of(task), HOLIDAYS) == datetime(2026, 10, 14, 12, 45)


def test_weeks_are_counted_from_the_pushed_start_not_the_planned_start() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    before = Task("p", id="p", planned_start=WED, effort_hours=32.5)  # 水〜火の 5 日 → 10/13 15:30 に終わる
    task = weekly_task("b", [[a], [a, b]], planned_start=WED, effort_hours=13.0, predecessors=["p"])
    # 開始は 10/13 15:30。第1週(10/13〜19)は 1 人なので、水・木の 13h で 10/15 15:30(開始予定から数えると水曜が第2週で、10/14 に終わる)
    assert effective_end(task, project_of(before, task), HOLIDAYS) == datetime(2026, 10, 15, 15, 30)


def test_weekly_crews_make_workers_with_the_parameters_applied() -> None:
    a = Assignee("田中", 0.5)
    task = weekly_task("w", [[a]])
    [[worker]] = weekly_crews(task, project_of(task))
    assert worker.rate == pytest.approx(0.5)
    assert (worker.name, worker.allocation) == ("田中", 0.5)
    assert worker == Worker(0.5)  # 名前と割り当て率は比較に使わない


def test_consumed_slices_cover_the_whole_effort() -> None:
    slices = consumed_slices(WED, 40.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0), workers(1.0, 1.0)])
    assert slices[0][0] == WED and slices[-1][1] == datetime(2026, 10, 14, 12, 45)
    worked = sum(((right - left).total_seconds() / 3600) * sum(w.rate for w in active) for left, right, active in slices)
    assert worked == pytest.approx(40.0)
    assert consumed_slices(WED, 0.0, 6.5, OPEN, HOLIDAYS, weeks=[workers(1.0)]) == []
