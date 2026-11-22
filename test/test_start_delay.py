"""着工遅れ・停止の判定(要望 161)。2026-10-05 は月曜。"""

from datetime import date, datetime, timedelta

import pytest

from projectapp.models import (
    Actual,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)
from projectapp.start_delay import (
    DelayKind,
    StartDelay,
    chip_texts,
    missed_workdays,
    start_delays,
)
from projectapp.timeline import Schedule

NO_HOLIDAYS: dict[date, str] = {}


def delays(
    task: Task,
    now: datetime,
    *,
    grace: int = 0,
    holidays: dict[date, str] | None = None,
    others: list[Task] | None = None,
) -> list[StartDelay]:
    project = Project(
        "p",
        start_delay_grace=grace,
        sections=[Section("s", [*(others or []), task])],
    )
    h = holidays or NO_HOLIDAYS
    return start_delays(task, project, h, Schedule(project, h), now)


def task(
    start: datetime, *actuals: Actual, status: Status = Status.NOT_STARTED
) -> Task:
    return Task(
        "設計",
        planned_start=start,
        planned_end=start + timedelta(days=2),
        status=status,
        actuals=list(actuals),
    )


def day(n: int, hour: int = 9) -> datetime:
    """10/5(月)を n=0 とした日の hour 時。"""
    return datetime(2026, 10, 5, hour) + timedelta(days=n)


# --- missed_workdays ---


def test_missed_workdays_counts_only_workdays_in_the_range() -> None:
    fri, mon = date(2026, 10, 2), date(2026, 10, 5)
    count = missed_workdays
    assert count(fri, mon, NO_HOLIDAYS, include_first=True, include_last=False) == 1
    assert count(fri, mon, NO_HOLIDAYS, include_first=False, include_last=False) == 0
    assert count(fri, mon, NO_HOLIDAYS, include_first=True, include_last=True) == 2


def test_missed_workdays_skips_holidays_and_is_zero_for_a_reversed_range() -> None:
    holidays = {date(2026, 10, 6): "休"}
    mon, wed = date(2026, 10, 5), date(2026, 10, 7)
    assert (
        missed_workdays(mon, wed, holidays, include_first=True, include_last=False) == 1
    )
    assert (
        missed_workdays(wed, mon, NO_HOLIDAYS, include_first=True, include_last=True)
        == 0
    )


# --- 着工 ---


def test_a_start_one_workday_late_is_a_start_delay() -> None:
    result = delays(task(day(0, 12), Actual(day(1), day(1, 12))), day(3))
    assert result == [StartDelay(DelayKind.START, day(0, 12), day(1), 1)]


def test_a_start_on_the_planned_day_is_not_a_delay_even_if_the_time_is_later() -> None:
    assert delays(task(day(0, 9), Actual(day(0, 15), day(0, 17))), day(3)) == []


def test_a_weekend_start_picked_up_on_monday_is_not_a_delay() -> None:
    saturday = datetime(2026, 10, 3, 9)
    assert delays(task(saturday, Actual(day(0), day(0, 12))), day(3)) == []


def test_friday_to_monday_counts_one_workday() -> None:
    friday = datetime(2026, 10, 2, 9)
    result = delays(task(friday, Actual(day(0), day(0, 12))), day(3))
    assert [(d.kind, d.days) for d in result] == [(DelayKind.START, 1)]


def test_a_holiday_is_not_counted() -> None:
    holidays = {date(2026, 10, 6): "休"}
    result = delays(task(day(0), Actual(day(2), day(2, 12))), day(4), holidays=holidays)
    assert [(d.kind, d.days) for d in result] == [(DelayKind.START, 1)]


def test_the_grace_must_be_exceeded() -> None:
    late_one = task(day(0), Actual(day(1), day(1, 12)))
    assert delays(late_one, day(3), grace=1) == []
    late_two = task(day(0), Actual(day(2), day(2, 12)))
    assert [d.days for d in delays(late_two, day(4), grace=1)] == [2]


def test_a_predecessor_pushes_the_start_so_the_count_begins_there() -> None:
    first = Task(
        "先行",
        planned_start=day(0),
        planned_end=day(2, 15),
        planned_end_manual=True,
    )
    second = task(day(0), Actual(day(3), day(3, 12)))
    second.predecessors = [first.id]
    result = delays(second, day(5), others=[first])
    # 先行の完了(10/7)から数えるので、10/5 からの 3 日ではなく 1 日
    assert [(d.kind, d.days) for d in result] == [(DelayKind.START, 1)]


# --- 未着手 ---


def test_an_unstarted_task_past_its_start_is_a_delay_that_runs_until_now() -> None:
    result = delays(task(day(0)), day(2, 10))
    assert result == [StartDelay(DelayKind.UNSTARTED, day(0), day(2, 10), 2, True)]


def test_today_is_not_counted_for_an_unstarted_task() -> None:
    assert delays(task(day(0)), day(0, 15)) == []
    assert [d.days for d in delays(task(day(0)), day(1, 9))] == [1]


@pytest.mark.parametrize("status", [Status.RUNNING, Status.PAUSED, Status.DONE])
def test_other_statuses_without_actuals_are_not_unstarted(status: Status) -> None:
    assert delays(task(day(0), status=status), day(4)) == []


# --- 停止 ---


def test_a_missed_workday_between_intervals_is_a_stop() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), Actual(day(2), day(2, 12))), day(3)
    )
    assert result == [StartDelay(DelayKind.STOP, day(0, 12), day(2), 1)]


def test_the_next_day_is_not_a_stop() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), Actual(day(1), day(1, 12))), day(3)
    )
    assert result == []


def test_a_weekend_between_intervals_is_not_a_stop() -> None:
    result = delays(
        task(day(0), Actual(day(-3), day(-3, 12)), Actual(day(0), day(0, 12))), day(3)
    )
    assert [d.kind for d in result] == []


def test_a_paused_task_is_stopped_until_now() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), status=Status.PAUSED), day(3, 10)
    )
    assert result == [StartDelay(DelayKind.STOP, day(0, 12), day(3, 10), 2, True)]


def test_a_running_task_with_a_closed_interval_is_not_stopped() -> None:
    result = delays(
        task(day(0), Actual(day(0), day(0, 12)), status=Status.RUNNING), day(3, 10)
    )
    assert result == []


def test_overlapping_or_reversed_intervals_do_not_raise_or_stop() -> None:
    reversed_ = task(day(0), Actual(day(2), day(2, 12)), Actual(day(0), day(0, 12)))
    assert [d.kind for d in delays(reversed_, day(3)) if d.kind is DelayKind.STOP] == []
    overlap = task(day(0), Actual(day(0), day(2)), Actual(day(1), day(1, 12)))
    assert [d.kind for d in delays(overlap, day(3)) if d.kind is DelayKind.STOP] == []


def test_a_start_delay_and_a_stop_can_both_be_reported() -> None:
    result = delays(
        task(day(0), Actual(day(1), day(1, 12)), Actual(day(3), day(3, 12))), day(5)
    )
    assert [d.kind for d in result] == [DelayKind.START, DelayKind.STOP]


# --- 対象外 ---


def test_a_checkpoint_has_no_delay() -> None:
    checkpoint = Task("節目", kind=TaskKind.CHECKPOINT, deadline=day(0))
    assert delays(checkpoint, day(4)) == []


def test_a_task_without_a_start_has_no_delay() -> None:
    assert delays(Task("日付なし"), day(4)) == []


# --- チップの文言 ---


def test_the_chip_texts_name_each_kind() -> None:
    result = chip_texts(
        [
            StartDelay(DelayKind.START, day(0, 12), day(2), 2),
            StartDelay(DelayKind.STOP, day(3, 12), day(5), 1),
            StartDelay(DelayKind.STOP, day(6, 12), day(8, 10), 1, True),
        ]
    )
    assert [(kind, text) for kind, text, _ in result] == [
        (DelayKind.START, "着工 +2日"),
        (DelayKind.STOP, "停止 +2日"),
    ]
    assert "10/05" in result[0][2] and "10/07" in result[0][2]
    assert result[1][2].count("\n") == 1  # 停止は区間ごとに 1 行
    assert "(今)" in result[1][2]


def test_the_unstarted_chip() -> None:
    [(kind, text, tip)] = chip_texts(
        [StartDelay(DelayKind.UNSTARTED, day(0), day(2, 10), 2, True)]
    )
    assert (kind, text) == (DelayKind.UNSTARTED, "未着手 +2日")
    assert "10/05" in tip
