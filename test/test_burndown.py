from datetime import date, datetime, timedelta
from time import perf_counter

import pytest

from projectapp.burndown import (
    BurnTask,
    Mark,
    compute_burndown,
    count_workdays,
    next_workday,
    planned_curve,
)
from projectapp.models import Change, HistoryEvent, Status, Task

ANCHOR = date(2026, 11, 1)  # 日曜。11/02(月)から数える
LAST = date(2026, 11, 8)  # 日曜


def bt(start: date | None, end: date | None, name: str = "x") -> BurnTask:
    return BurnTask(Task(name, id=name), (), start, end)


def test_count_workdays_skips_weekends_and_weekday_holidays() -> None:
    assert count_workdays(date(2026, 11, 2), date(2026, 11, 8), {}) == 5
    assert count_workdays(date(2026, 11, 2), date(2026, 11, 15), {}) == 10
    assert (
        count_workdays(date(2026, 11, 2), date(2026, 11, 8), {date(2026, 11, 4): "祝"})
        == 4
    )
    assert (
        count_workdays(date(2026, 11, 2), date(2026, 11, 8), {date(2026, 11, 7): "祝"})
        == 5
    )
    assert count_workdays(date(2026, 11, 7), date(2026, 11, 9), {}) == 1
    assert count_workdays(date(2026, 11, 9), date(2026, 11, 8), {}) == 0


def test_next_workday() -> None:
    assert next_workday(date(2026, 11, 2), {}) == date(2026, 11, 2)
    assert next_workday(date(2026, 11, 7), {}) == date(2026, 11, 9)
    assert next_workday(date(2026, 11, 7), {date(2026, 11, 9): "祝"}) == date(
        2026, 11, 10
    )


def test_planned_curve_burns_straight_over_the_workdays_of_the_plan() -> None:
    curve = planned_curve(
        [bt(date(2026, 11, 2), date(2026, 11, 4))], [10.0], ANCHOR, LAST, {}
    )
    assert curve == pytest.approx((20 / 3, 10 / 3, 0, 0, 0, 0, 0))


def test_planned_curve_stops_above_zero_when_the_plan_runs_past_the_end() -> None:
    # 金(11/06)〜翌週火(11/10)は稼働日 3 日(金・月・火)。11/06 に 1 日分進み、土日は動かない
    curve = planned_curve(
        [bt(date(2026, 11, 6), date(2026, 11, 10))], [10.0], ANCHOR, LAST, {}
    )
    assert curve == pytest.approx((10, 10, 10, 10, 20 / 3, 20 / 3, 20 / 3))


def test_planned_curve_finishes_an_overdue_task_on_the_next_workday() -> None:
    curve = planned_curve(
        [bt(date(2026, 10, 28), date(2026, 10, 29))], [6.0], ANCHOR, LAST, {}
    )
    assert curve == pytest.approx((0, 0, 0, 0, 0, 0, 0))


def test_planned_curve_from_a_friday_anchor_finishes_on_monday() -> None:
    curve = planned_curve(
        [bt(date(2026, 10, 28), date(2026, 10, 29))],
        [6.0],
        date(2026, 11, 6),
        date(2026, 11, 10),
        {},
    )
    assert curve == pytest.approx((6, 6, 0, 0))  # 11/07 土・11/08 日・11/09 月で 0


def test_planned_curve_keeps_a_task_whose_plan_is_only_on_days_off() -> None:
    # 土(11/07)〜日(11/08)だけの予定は、次の稼働日(11/09)に終える扱い。期間の中では動かない
    curve = planned_curve(
        [bt(date(2026, 11, 7), date(2026, 11, 8))], [3.0], ANCHOR, LAST, {}
    )
    assert curve == pytest.approx((3, 3, 3, 3, 3, 3, 3))


def test_planned_curve_does_not_move_a_task_without_a_readable_plan() -> None:
    tasks = [bt(None, None, "a"), bt(date(2026, 11, 2), None, "b")]
    assert planned_curve(tasks, [2.0, 3.0], ANCHOR, LAST, {}) == pytest.approx((5,) * 7)


def test_planned_curve_treats_an_end_before_the_start_as_one_day() -> None:
    curve = planned_curve(
        [bt(date(2026, 11, 4), date(2026, 11, 2))], [4.0], ANCHOR, LAST, {}
    )
    assert curve == pytest.approx((4, 4, 0, 0, 0, 0, 0))  # 11/04 の 1 日で終える


def test_planned_curve_does_not_count_a_holiday_as_a_workday() -> None:
    holidays = {date(2026, 11, 3): "祝日"}
    curve = planned_curve(
        [bt(date(2026, 11, 2), date(2026, 11, 4))], [10.0], ANCHOR, LAST, holidays
    )
    assert curve == pytest.approx((5, 5, 0, 0, 0, 0, 0))


def test_planned_curve_ignores_tasks_without_remaining_work() -> None:
    assert (
        planned_curve(
            [bt(date(2026, 11, 2), date(2026, 11, 4))], [0.0], ANCHOR, LAST, {}
        )
        == (0.0,) * 7
    )


def test_planned_curve_is_empty_when_there_are_no_days_after_the_anchor() -> None:
    assert planned_curve([bt(None, None)], [1.0], LAST, LAST, {}) == ()
    assert planned_curve([bt(None, None)], [1.0], date(2026, 11, 9), LAST, {}) == ()


FIRST = date(2026, 11, 2)  # 月曜
END = date(2026, 11, 8)  # 日曜
SINCE = datetime(2026, 11, 1, 9)
NOW = datetime(2026, 11, 4, 12)  # 水曜の昼


def ev(task: str, at: datetime, **fields: tuple) -> HistoryEvent:
    return HistoryEvent(
        task, at, tuple(Change(n, b, a) for n, (b, a) in fields.items())
    )


def actual_tasks() -> list[BurnTask]:
    """A: 10h。11/03 に実行中・進捗度 50%、11/04 に終了。B: 4h で動かない。C: 6h で 11/03 に作られた。"""
    a = Task("A", id="a", effort_hours=10, status=Status.DONE, progress=50)
    b = Task("B", id="b", effort_hours=4)
    c = Task("C", id="c", effort_hours=6)
    return [
        BurnTask(
            a,
            (
                ev(
                    "a",
                    datetime(2026, 11, 3, 10),
                    status=("未着手", "実行中"),
                    progress=(None, 50),
                ),
                ev("a", datetime(2026, 11, 4, 9), status=("実行中", "終了")),
            ),
            None,
            None,
        ),
        BurnTask(b, (), None, None),
        BurnTask(
            c,
            (
                ev(
                    "c",
                    datetime(2026, 11, 3, 15),
                    status=(None, "未着手"),
                    progress=(None, None),
                    effort=(None, 6),
                ),
            ),
            None,
            None,
        ),
    ]


def test_actual_line_follows_the_history_day_by_day() -> None:
    result = compute_burndown(actual_tasks(), FIRST, END, NOW, SINCE, {})
    assert result.known and result.count == 3
    assert result.initial == 14.0
    assert result.actual == (
        14.0,
        15.0,
        10.0,
    )  # 11/02 の終わり・11/03 の終わり・今(11/04 昼)
    assert result.today_index == 2 and result.now_fraction == 0.5
    assert result.workdays == (True, True, True, True, True, False, False)


def test_a_task_created_in_the_period_raises_the_actual_line_but_not_the_first_plan() -> (
    None
):
    result = compute_burndown(actual_tasks(), FIRST, END, NOW, SINCE, {})
    assert (
        result.planned == (14.0,) * 7
    )  # 予定が読めないタスクは動かず、C(期間中に作成)は入らない


def test_the_future_line_starts_at_the_actual_value_now() -> None:
    result = compute_burndown(actual_tasks(), FIRST, END, NOW, SINCE, {})
    assert result.future == (10.0,) * 5  # 11/04(今)〜11/08
    assert (
        result.rest == 0.0 and result.required == 0.0
    )  # 11/05・11/06 の 2 稼働日が残る


def test_marks_show_the_day_progress_was_first_entered_not_the_creation() -> None:
    result = compute_burndown(actual_tasks(), FIRST, END, NOW, SINCE, {})
    assert result.marks == (Mark(date(2026, 11, 3), ("A",)),)


def test_unset_lists_running_or_paused_tasks_without_progress() -> None:
    running = Task("走", id="r", status=Status.RUNNING)
    paused = Task("停", id="p", status=Status.PAUSED)
    waiting = Task("待", id="w")
    done = Task("終", id="d", status=Status.DONE)
    entered = Task("入", id="e", status=Status.RUNNING, progress=10)
    tasks = [
        BurnTask(t, (), None, None) for t in (running, paused, waiting, done, entered)
    ]
    assert compute_burndown(tasks, FIRST, END, NOW, SINCE, {}).unset == ("走", "停")


def test_a_period_starting_before_the_history_is_unknown() -> None:
    result = compute_burndown(
        actual_tasks(), FIRST, END, NOW, datetime(2026, 11, 3), {}
    )
    assert not result.known and result.since == date(2026, 11, 3)
    assert result.actual == () and result.future == ()


def test_no_history_at_all_is_unknown() -> None:
    result = compute_burndown(actual_tasks(), FIRST, END, NOW, None, {})
    assert not result.known and result.since is None


def test_before_the_period_there_is_no_actual_line_and_no_pace() -> None:
    result = compute_burndown(
        actual_tasks(),
        FIRST,
        END,
        datetime(2026, 10, 30, 12),
        datetime(2026, 10, 20),
        {},
    )
    assert result.known and result.actual == () and result.future == ()
    assert result.today_index is None and result.required is None
    assert len(result.planned) == 7


def test_after_the_period_the_actual_line_covers_every_day_and_there_is_no_future() -> (
    None
):
    result = compute_burndown(
        actual_tasks(), FIRST, END, datetime(2026, 11, 10, 12), SINCE, {}
    )
    assert len(result.actual) == 7 and result.today_index is None
    assert result.future == () and result.required is None and not result.behind


def test_on_the_last_workday_there_is_no_required_pace() -> None:
    result = compute_burndown(
        actual_tasks(), FIRST, date(2026, 11, 6), datetime(2026, 11, 6, 12), SINCE, {}
    )
    assert result.today_index == 4
    assert result.future == (result.actual[-1],)
    assert result.required is None


def pace_task(progress_now: int, second_event: bool) -> BurnTask:
    """P: 40h、予定は 11/02〜11/13。10/25 に進捗度 25%、(second_event なら)11/03 に 75%。"""
    task = Task(
        "P", id="p", effort_hours=40, status=Status.RUNNING, progress=progress_now
    )
    events = [ev("p", datetime(2026, 10, 25, 10), progress=(None, 25))]
    if second_event:
        events.append(ev("p", datetime(2026, 11, 3, 10), progress=(25, 75)))
    return BurnTask(task, tuple(events), date(2026, 11, 2), date(2026, 11, 13))


PACE_SINCE = datetime(2026, 10, 19, 9)
PACE_LAST = date(2026, 11, 13)


def test_pace_when_ahead_of_the_plan() -> None:
    result = compute_burndown(
        [pace_task(75, True)], FIRST, PACE_LAST, NOW, PACE_SINCE, {}
    )
    assert result.actual[-1] == pytest.approx(10.0)
    assert (
        result.recent == pytest.approx(3.0) and result.recent_days == 10
    )  # (40 − 10) ÷ 10
    assert result.future[-1] == pytest.approx(0.0)
    assert result.required == pytest.approx(10 / 7)  # 11/05〜11/13 の 7 稼働日
    assert (
        result.ahead and not result.behind
    )  # 今 10h は、当初の予定の今日の終わり 21h 以下


def test_pace_when_behind_the_plan() -> None:
    result = compute_burndown(
        [pace_task(25, False)], FIRST, PACE_LAST, NOW, PACE_SINCE, {}
    )
    assert result.recent == pytest.approx(1.0)  # 10/21 の 40h → 今 30h を 10 稼働日で
    assert result.required == pytest.approx(30 / 7)
    assert result.behind and not result.ahead


def test_recent_pace_is_missing_when_the_history_is_too_short() -> None:
    result = compute_burndown(actual_tasks(), FIRST, END, NOW, SINCE, {})
    assert result.recent is None and result.recent_days == 0 and not result.behind


def test_recent_pace_never_goes_below_zero_when_the_work_grew() -> None:
    grew = Task("G", id="g", effort_hours=20, status=Status.RUNNING, progress=0)
    item = BurnTask(
        grew,
        (ev("g", datetime(2026, 11, 3, 10), effort=(10, 20)),),
        date(2026, 11, 2),
        date(2026, 11, 13),
    )
    result = compute_burndown([item], FIRST, PACE_LAST, NOW, PACE_SINCE, {})
    assert result.recent == 0.0


def test_a_year_of_history_is_fast() -> None:
    first = date(2026, 1, 1)
    last = first + timedelta(days=399)
    tasks = []
    for i in range(300):
        task = Task(
            f"t{i}", id=f"t{i}", effort_hours=8, status=Status.RUNNING, progress=87
        )
        events = tuple(
            ev(
                task.id,
                datetime(2026, 1, 1, 9) + timedelta(days=j * 13, hours=i % 8),
                progress=(None if j == 0 else (j - 1) * 3, j * 3),
            )
            for j in range(30)
        )
        tasks.append(
            BurnTask(
                task,
                events,
                first + timedelta(days=i % 50),
                first + timedelta(days=50 + i % 300),
            )
        )
    started = perf_counter()
    result = compute_burndown(
        tasks, first, last, datetime(2027, 2, 4, 12), datetime(2025, 12, 31), {}
    )
    assert perf_counter() - started < 3.0
    assert len(result.actual) == 400 and len(result.planned) == 400
