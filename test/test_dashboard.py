from datetime import date, datetime

import pytest

from projectapp.dashboard import Period, PeriodKind, period_for, summarize_progress
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
