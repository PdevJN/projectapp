from datetime import date, datetime, time

import pytest

from projectapp.dashboard import Period, _member_spans, summarize_workload
from projectapp.handoff import build_todos
from projectapp.models import Actual, Assignee, Member, Project, Status, Task, union_assignees
from projectapp.timeline import (
    Overload,
    Worker,
    calc_end,
    clip_overloads,
    consumed_slices,
    counted_pieces,
    crew_on,
    crew_pieces,
    effective_end,
    overallocations,
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


def test_crew_pieces_cut_at_midnight_every_seven_days_from_the_start() -> None:
    a, b = Assignee("田中"), Assignee("鈴木")
    task = weekly_task("w", [[a], [b]])
    end = datetime(2026, 10, 20, 15, 30)
    assert crew_pieces(task, WED, end) == [(WED, datetime(2026, 10, 14), [a]), (datetime(2026, 10, 14), end, [b])]


def test_crew_pieces_stop_where_the_task_ends() -> None:
    a, b, c = Assignee("田中"), Assignee("鈴木"), Assignee("田中", 0.5)
    task = weekly_task("w", [[a], [b], [c]])
    end = datetime(2026, 10, 10, 12)  # 第1週の中で終わる
    assert crew_pieces(task, WED, end) == [(WED, end, [a])]
    later = datetime(2026, 10, 16, 12)  # 第2週の中で終わる
    assert [crew for _, _, crew in crew_pieces(task, WED, later)] == [[a], [b]]


def test_crew_pieces_of_a_plain_task_is_one_piece() -> None:
    a = Assignee("田中")
    end = datetime(2026, 10, 20)
    assert crew_pieces(Task("p", assignees=[a]), WED, end) == [(WED, end, [a])]


def overload_project() -> Project:
    first, second = Assignee("田中"), Assignee("鈴木")
    # 田中は第1週、鈴木は第2週にこのタスクを担当する(工数 65h は 1 人で 10/20 15:30 まで)
    t1 = weekly_task("t1", [[first], [second]], planned_start=WED, effort_hours=65.0)
    end = datetime(2026, 10, 20, 15, 30)
    t2 = Task("t2", id="t2", planned_start=WED, planned_end=end, assignees=[Assignee("田中", 0.5)])
    t3 = Task("t3", id="t3", planned_start=WED, planned_end=end, assignees=[Assignee("鈴木", 0.5)])
    return project_of(t1, t2, t3)


def test_overloads_are_counted_per_week_of_the_crew() -> None:
    proj = overload_project()
    boundary = datetime(2026, 10, 14)
    assert overallocations(proj, HOLIDAYS) == [
        Overload("田中", WED, boundary, 1.5),
        Overload("鈴木", boundary, datetime(2026, 10, 20, 15, 30), 1.5),
    ]


def test_clip_overloads_keeps_only_the_weeks_of_the_member() -> None:
    proj = overload_project()
    overloads = overallocations(proj, HOLIDAYS)
    t1, t2, t3 = proj.tasks
    assert clip_overloads(t1, proj, HOLIDAYS, overloads) == overloads  # t1 は 2 人が各週に入る
    assert clip_overloads(t2, proj, HOLIDAYS, overloads) == [overloads[0]]  # 田中は第1週だけ超過
    assert clip_overloads(t3, proj, HOLIDAYS, overloads) == [overloads[1]]


def test_counted_pieces_skip_non_members_and_uncounted_tasks() -> None:
    proj = overload_project()
    ghost = weekly_task("g", [[Assignee("佐藤")], [Assignee("佐藤"), Assignee("田中")]], planned_start=WED, effort_hours=65.0)
    proj.tasks.append(ghost)
    pieces = counted_pieces(ghost, proj, HOLIDAYS)
    assert [[a.name for a in crew] for _, _, crew in pieces] == [[], ["田中"]]
    finished = weekly_task("f", [[Assignee("田中")]], planned_start=WED, effort_hours=6.5, status=Status.DONE)
    assert counted_pieces(finished, proj, HOLIDAYS) == []


def split_project() -> Project:
    # 10/5(月)〜10/19(月)。田中が第1週、鈴木が第2週以降
    task = weekly_task(
        "t",
        [[Assignee("田中")], [Assignee("鈴木")]],
        planned_start=MON,
        planned_end=datetime(2026, 10, 19, 15, 30),
        actuals=[Actual(datetime(2026, 10, 13, 9), datetime(2026, 10, 13, 11))],
    )
    return project_of(task)


def test_member_spans_follow_the_weeks_of_the_crew() -> None:
    spans = _member_spans(split_project(), HOLIDAYS, None)
    boundary = datetime(2026, 10, 12)
    assert spans == {
        "田中": [(MON, boundary, 1.0)],
        "鈴木": [(boundary, datetime(2026, 10, 19, 15, 30), 1.0)],
    }


def test_workload_plans_each_week_for_its_own_crew_and_splits_the_actual_by_the_week() -> None:
    period = Period(date(2026, 10, 5), date(2026, 10, 25))
    rows = {r.name: r for r in summarize_workload(split_project(), period, datetime(2026, 10, 20), HOLIDAYS)}
    assert rows["田中"].planned_hours == pytest.approx(32.5)  # 10/5〜9 の 5 日
    assert rows["鈴木"].planned_hours == pytest.approx(39.0)  # 10/12〜16 と 10/19 の 6 日
    assert rows["田中"].actual_hours == pytest.approx(0.0)
    assert rows["鈴木"].actual_hours == pytest.approx(2.0)  # 10/13 は第2週(鈴木)


def test_handoff_estimates_each_member_from_the_weeks_they_work() -> None:
    a, b = Assignee("田中"), Assignee("鈴木", 0.5)
    task = weekly_task("t", [[a], [a, b]], planned_start=MON, effort_hours=50.0)
    project = project_of(task)
    # 第1週 32.5h は田中だけ。残り 17.5h は第2週の 田中+鈴木(0.5) で、10/12 に 9.75h、10/13 に 7.75h(= 5.1667h の稼働)
    todos = build_todos(project, "田中", HOLIDAYS)
    assert todos.data["items"][0]["estimate_hours"] == pytest.approx(44.17)
    other = build_todos(project, "鈴木", HOLIDAYS)
    assert other.data["items"][0]["estimate_hours"] == pytest.approx(5.83)  # 11.6667h の稼働 × 割り当て率 0.5


def test_handoff_estimate_of_a_plain_task_is_unchanged() -> None:
    task = Task("p", id="p", planned_start=MON, effort_hours=13.0, assignees=[Assignee("田中", 0.5), Assignee("鈴木")])
    todos = build_todos(project_of(task), "田中", HOLIDAYS)
    assert todos.data["items"][0]["estimate_hours"] == pytest.approx(round(13.0 * 0.5 / 1.5, 2))  # 換算率の合計は 0.5 + 1.0。見積もりは小数 2 桁
