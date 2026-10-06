from datetime import date, datetime

import pytest

from projectapp.dashboard import (
    UNASSIGNED,
    DueRow,
    Period,
    PeriodKind,
    period_for,
    summarize,
    summarize_due,
    summarize_loads,
    summarize_progress,
    summarize_workload,
)
from projectapp.timeline import overallocations
from projectapp.models import Actual, Member, Project, Status, Task

TODAY = date(2026, 10, 7)  # 水曜
NOW = datetime(2026, 10, 7, 12)


def project_of(*tasks: Task, members: list[Member] | None = None) -> Project:
    chosen = [Member("田中", 1.0)] if members is None else members
    return Project("P", base_date=date(2026, 10, 5), members=chosen, tasks=list(tasks))


@pytest.mark.parametrize(
    ("today", "start", "end"),
    [
        (date(2026, 10, 7), date(2026, 10, 5), date(2026, 10, 11)),
        (date(2026, 10, 5), date(2026, 10, 5), date(2026, 10, 11)),  # 月曜
        (date(2026, 10, 11), date(2026, 10, 5), date(2026, 10, 11)),  # 日曜
        (date(2026, 12, 31), date(2026, 12, 28), date(2027, 1, 3)),  # 年またぎ
    ],
)
def test_the_week_runs_from_monday_to_sunday(today: date, start: date, end: date) -> None:
    assert period_for(PeriodKind.WEEK, today, project_of(), {}) == Period(start, end)


@pytest.mark.parametrize(
    ("today", "start", "end"),
    [
        (date(2026, 10, 7), date(2026, 10, 1), date(2026, 10, 31)),
        (date(2026, 12, 15), date(2026, 12, 1), date(2026, 12, 31)),
        (date(2028, 2, 10), date(2028, 2, 1), date(2028, 2, 29)),  # うるう年
    ],
)
def test_the_month_runs_from_the_first_to_the_last_day(today: date, start: date, end: date) -> None:
    assert period_for(PeriodKind.MONTH, today, project_of(), {}) == Period(start, end)


def test_the_whole_period_is_today_when_nothing_has_a_date() -> None:
    assert period_for(PeriodKind.ALL, TODAY, project_of(Task("a")), {}) == Period(TODAY, TODAY)


def test_the_whole_period_spans_planned_dates_deadlines_and_actuals() -> None:
    task = Task(
        "a",
        planned_start=datetime(2026, 10, 6, 9),
        planned_end=datetime(2026, 10, 9, 12),
        deadline=datetime(2026, 10, 20, 17),
        actuals=[Actual(datetime(2026, 10, 3, 9), datetime(2026, 10, 3, 12))],
    )
    assert period_for(PeriodKind.ALL, TODAY, project_of(task), {}) == Period(date(2026, 10, 3), date(2026, 10, 20))


def test_a_period_lists_its_days_and_its_bounds() -> None:
    period = Period(date(2026, 10, 5), date(2026, 10, 7))
    assert period.days() == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    assert period.bounds() == (datetime(2026, 10, 5), datetime(2026, 10, 8))


def test_progress_is_the_effort_weighted_average() -> None:
    a = Task("A", effort_hours=10, status=Status.RUNNING, actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12), progress=50)])
    b = Task("B", status=Status.DONE)  # 工数なしは重み 1。終了は 100%
    c = Task("C", effort_hours=10)  # 進捗の入力なしは 0%
    progress = summarize_progress(project_of(a, b, c), {}, NOW)
    assert progress.percent == pytest.approx(600 / 21)
    assert progress.counts == {Status.NOT_STARTED: 1, Status.RUNNING: 1, Status.PAUSED: 0, Status.DONE: 1}


def test_progress_is_none_without_tasks() -> None:
    progress = summarize_progress(project_of(), {}, NOW)
    assert progress.percent is None
    assert set(progress.counts.values()) == {0}
    assert progress.overdue == []


def test_overdue_rows_use_the_earliest_passed_limit_and_are_sorted() -> None:
    late = Task("late", status=Status.RUNNING, deadline=datetime(2026, 10, 6, 17), assignee="田中")
    ended = Task(
        "ended",
        status=Status.RUNNING,
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 6, 12),
        deadline=datetime(2026, 10, 9),
    )
    both = Task(
        "both",
        status=Status.PAUSED,
        planned_start=datetime(2026, 10, 4, 9),
        planned_end=datetime(2026, 10, 5, 17),
        deadline=datetime(2026, 10, 6, 17),
    )
    fine = Task("fine", deadline=datetime(2026, 10, 8))
    done_late = Task(
        "done",
        status=Status.DONE,
        deadline=datetime(2026, 10, 6),
        actuals=[Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 7, 9))],
    )
    rows = summarize_progress(project_of(late, ended, both, fine, done_late), {}, NOW).overdue
    assert [(r.name, r.limit) for r in rows] == [
        ("both", datetime(2026, 10, 5, 17)),
        ("ended", datetime(2026, 10, 6, 12)),
        ("late", datetime(2026, 10, 6, 17)),
    ]
    assert rows[2].assignee == "田中"


WEEK = Period(date(2026, 10, 5), date(2026, 10, 11))


def span_task(name: str, start_day: int, end_day: int, allocation: float, **kwargs) -> Task:
    return Task(
        name,
        planned_start=datetime(2026, 10, start_day, 9),
        planned_end=datetime(2026, 10, end_day, 17),
        assignee="田中",
        allocation=allocation,
        **kwargs,
    )


def test_load_averages_over_workdays_and_tracks_the_peak() -> None:
    stats = summarize_loads(project_of(span_task("a", 5, 7, 0.5)), WEEK, {})["田中"]
    assert stats.average == pytest.approx(0.3)  # 月〜水に 50%、木・金は 0
    assert stats.peak == 0.5
    assert stats.overload_days == 0


def test_load_counts_days_over_one_hundred_percent_like_the_stripes() -> None:
    project = project_of(span_task("a", 5, 6, 0.6), span_task("b", 5, 6, 0.6))
    stats = summarize_loads(project, WEEK, {})["田中"]
    assert (stats.peak, stats.overload_days) == (pytest.approx(1.2), 2)
    assert stats.average == pytest.approx(0.48)
    assert overallocations(project, {})  # 縞と同じタスクの重なりを数えている


def test_exactly_one_hundred_percent_is_not_an_overload() -> None:
    project = project_of(span_task("a", 5, 6, 0.5), span_task("b", 5, 6, 0.5))
    assert summarize_loads(project, WEEK, {})["田中"].overload_days == 0


def test_finished_tasks_do_not_load_a_member() -> None:
    project = project_of(span_task("a", 5, 7, 0.9, status=Status.DONE))
    stats = summarize_loads(project, WEEK, {})["田中"]
    assert (stats.average, stats.peak, stats.overload_days) == (0.0, 0.0, 0)


def test_holidays_are_not_workdays() -> None:
    stats = summarize_loads(project_of(span_task("a", 5, 7, 0.5)), WEEK, {date(2026, 10, 6): "祝"})["田中"]
    assert stats.average == pytest.approx(0.25)  # 月・水・木・金の 4 日で割る


def test_a_period_without_workdays_is_zero_and_does_not_divide() -> None:
    weekend = Period(date(2026, 10, 10), date(2026, 10, 11))
    stats = summarize_loads(project_of(span_task("a", 5, 12, 0.5)), weekend, {})["田中"]
    assert (stats.average, stats.peak, stats.overload_days) == (0.0, 0.0, 0)


def test_loads_list_the_members_in_order_and_skip_non_members() -> None:
    members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    stranger = span_task("x", 5, 7, 0.5)
    stranger.assignee = "鈴木"
    loads = summarize_loads(project_of(span_task("a", 5, 7, 0.5), stranger, members=members), WEEK, {})
    assert list(loads) == ["田中", "佐藤"]
    assert loads["佐藤"].peak == 0.0


DAY = Period(date(2026, 10, 6), date(2026, 10, 6))


def test_planned_hours_use_allocation_and_daily_hours_and_include_finished_tasks() -> None:
    project = project_of(span_task("a", 5, 7, 0.5, status=Status.DONE))
    rows = summarize_workload(project, DAY, NOW, {})
    assert [(r.name, r.planned_hours) for r in rows] == [("田中", 0.5 * 6.5)]
    assert summarize_workload(project, Period(date(2026, 10, 5), date(2026, 10, 7)), NOW, {})[0].planned_hours == pytest.approx(9.75)


def test_unassigned_work_is_grouped_and_only_listed_when_it_has_hours() -> None:
    unassigned = Task("u", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 6, 17))
    members = [Member("田中", 1.0), Member("佐藤", 1.0)]
    rows = summarize_workload(project_of(unassigned, members=members), DAY, NOW, {})
    assert [(r.name, r.planned_hours) for r in rows] == [("田中", 0.0), ("佐藤", 0.0), (UNASSIGNED, 6.5)]
    assert [r.name for r in summarize_workload(project_of(members=members), DAY, NOW, {})] == ["田中", "佐藤"]


def test_actual_hours_clip_to_the_period_and_run_until_now() -> None:
    crossing = Actual(datetime(2026, 10, 5, 22), datetime(2026, 10, 6, 2))  # 期間内は 2 時間
    running = Actual(datetime(2026, 10, 6, 9))  # now(11:30)まで 2.5 時間
    outside = Actual(datetime(2026, 10, 1, 9), datetime(2026, 10, 1, 12))
    project = project_of(Task("a", assignee="田中", actuals=[crossing, running, outside]))
    rows = summarize_workload(project, DAY, datetime(2026, 10, 6, 11, 30), {})
    assert rows[0].actual_hours == pytest.approx(4.5)


def test_dashboard_totals_add_up_the_rows() -> None:
    project = project_of(span_task("a", 6, 6, 1.0, actuals=[Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 12))]))
    dashboard = summarize(project, DAY, NOW, {})
    assert dashboard.planned_total == pytest.approx(6.5)
    assert dashboard.actual_total == pytest.approx(3.0)
    assert dashboard.period == DAY
    assert list(dashboard.loads) == ["田中"]


def test_due_rows_list_deadlines_and_planned_ends_in_the_period_sorted() -> None:
    both = Task(
        "t1",
        assignee="田中",
        deadline=datetime(2026, 10, 8, 17),
        planned_start=datetime(2026, 10, 6, 9),
        planned_end=datetime(2026, 10, 9, 12),
    )
    late = Task("late", status=Status.RUNNING, deadline=datetime(2026, 10, 6, 17))
    edge_in = Task("in", deadline=datetime(2026, 10, 5, 0, 0))  # 期間の開始ちょうどは入る
    edge_out = Task("out", deadline=datetime(2026, 10, 12, 0, 0))  # 終了日の翌日 0 時は入らない
    outside = Task("far", deadline=datetime(2026, 10, 20, 17))
    done = Task("done", status=Status.DONE, deadline=datetime(2026, 10, 7, 9))
    rows = summarize_due(project_of(both, late, edge_in, edge_out, outside, done), WEEK, NOW, {})
    assert rows == [
        DueRow(datetime(2026, 10, 5, 0, 0), "締切", "in", None, True),
        DueRow(datetime(2026, 10, 6, 17), "締切", "late", None, True),
        DueRow(datetime(2026, 10, 8, 17), "締切", "t1", "田中", False),
        DueRow(datetime(2026, 10, 9, 12), "完了予定", "t1", "田中", False),
    ]
