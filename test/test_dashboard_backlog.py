from datetime import date, datetime

from projectapp.dashboard import UNASSIGNED, Period, PeriodKind, summarize, summarize_backlog
from projectapp.models import Actual, Assignee, Member, Project, Status, Task, TaskKind

NOW = datetime(2026, 10, 7, 12)  # 水曜
WEEK = Period(date(2026, 10, 5), date(2026, 10, 11))


def project_of(*tasks: Task, members: list[Member] | None = None) -> Project:
    chosen = [Member("田中", 1.0)] if members is None else members
    return Project("P", base_date=date(2026, 10, 5), members=chosen, tasks=list(tasks))


def todo(name: str, effort: float, **kwargs: object) -> Task:
    return Task(name, planned_start=datetime(2026, 10, 6, 9), effort_hours=effort, **kwargs)  # type: ignore[arg-type]


def test_not_started_counts_in_full_and_done_checkpoints_and_summaries_are_left_out() -> None:
    project = project_of(
        todo("未着手", 6.5),
        todo("終了", 10, status=Status.DONE),
        Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 8, 17)),
    )
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.hours == 6.5
    assert backlog.unset_count == 0


def test_running_and_paused_tasks_count_the_rest_after_the_progress() -> None:
    project = project_of(
        todo("未着手", 6.5),
        todo("実行中", 10, status=Status.RUNNING, progress=40),
        todo("一時停止", 10, status=Status.PAUSED, progress=25),
    )
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.hours == 6.5 + 6 + 7.5
    assert backlog.by_status == {Status.NOT_STARTED: 6.5, Status.RUNNING: 6, Status.PAUSED: 7.5}


def test_without_progress_the_worked_intervals_are_taken_off_by_the_conversion_rate() -> None:
    worked = [Actual(datetime(2026, 10, 6, 9), datetime(2026, 10, 6, 13))]  # 4h
    project = project_of(
        todo("実行中", 10, status=Status.RUNNING, assignees=[Assignee("田中")], actuals=worked),
        members=[Member("田中", 1.0)],
    )
    assert summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}).hours == 6
    half = project_of(
        todo("実行中", 10, status=Status.RUNNING, assignees=[Assignee("田中")], actuals=worked),
        members=[Member("田中", 0.5)],
    )
    assert summarize_backlog(half, WEEK, PeriodKind.WEEK, NOW, {}).hours == 8  # 4h × 0.5 = 2h 消化


def test_a_running_interval_without_an_end_is_not_taken_off() -> None:
    running = [Actual(datetime(2026, 10, 7, 9), None)]
    project = project_of(todo("実行中", 10, status=Status.RUNNING, actuals=running))
    assert summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}).hours == 10


def test_a_running_task_at_full_progress_adds_nothing() -> None:
    project = project_of(todo("ほぼ終了", 10, status=Status.RUNNING, progress=100))
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {})
    assert (backlog.hours, backlog.unset_count) == (0, 0)


def test_running_and_paused_tasks_without_effort_are_counted_as_unset() -> None:
    project = project_of(todo("実行中", 0, status=Status.RUNNING), todo("停止", 0, status=Status.PAUSED))
    assert summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}).unset_count == 2


def test_the_member_filter_takes_the_members_share_of_the_rest() -> None:
    project = project_of(
        todo("共同", 10, status=Status.RUNNING, progress=50, assignees=[Assignee("田中", 0.75), Assignee("鈴木", 0.25)]),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
    )
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}, "田中")
    assert (backlog.hours, backlog.by_status) == (3.75, {Status.RUNNING: 3.75})  # 残り 5h の 75%


def test_tasks_without_effort_are_counted_apart_not_as_one_hour() -> None:
    project = project_of(todo("あり", 3), todo("なし", 0))
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {})
    assert (backlog.hours, backlog.unset_count) == (3, 1)


def test_required_people_divide_by_the_remaining_workdays_of_the_period() -> None:
    # 水・木・金の 3 日 × 6.5h = 19.5h。月・火は過ぎているので数えない
    project = project_of(todo("a", 19.5))
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.days == 3
    assert backlog.required == 1.0


def test_holidays_are_not_workdays() -> None:
    project = project_of(todo("a", 13))
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {date(2026, 10, 8): "休"})
    assert backlog.days == 2
    assert backlog.required == 1.0


def test_tasks_outside_the_period_are_not_counted_except_for_all() -> None:
    far = Task("来月", planned_start=datetime(2026, 11, 2, 9), effort_hours=8)
    project = project_of(todo("今週", 4), far)
    assert summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}).hours == 4
    assert summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {}).hours == 12


def test_all_period_runs_from_today_to_the_latest_end_of_the_counted_tasks() -> None:
    project = project_of(todo("a", 6.5, deadline=datetime(2026, 10, 9, 17)))
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {})
    assert backlog.days == 3  # 水・木・金


def test_all_period_without_an_end_has_no_required_people() -> None:
    project = project_of(Task("日程なし", effort_hours=5))
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {})
    assert (backlog.hours, backlog.days, backlog.required) == (5, None, None)


def test_all_period_ending_in_the_past_still_counts_today_as_one_workday() -> None:
    project = project_of(Task("過去", planned_start=datetime(2026, 9, 1, 9), effort_hours=5))
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, NOW, {})
    assert (backlog.days, backlog.required) == (1, 5 / 6.5)  # 全部が遅れていても、今日 1 日で終える場合を示す


def test_all_period_with_everything_overdue_starts_at_the_next_workday_on_a_weekend() -> None:
    sunday = datetime(2026, 10, 11, 12)
    project = project_of(Task("過去", planned_start=datetime(2026, 9, 1, 9), effort_hours=6.5))
    backlog = summarize_backlog(project, WEEK, PeriodKind.ALL, sunday, {})
    assert (backlog.days, backlog.required) == (1, 1.0)


def test_supply_is_the_sum_of_relative_ratios_and_shortfall_follows() -> None:
    project = project_of(todo("a", 13), todo("b", 13), todo("c", 13), members=[Member("田中", 1.0), Member("鈴木", 0.5)])
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.supply == 1.5
    assert backlog.required == 2.0
    assert backlog.shortfall == 0.5


def test_supply_uses_the_clamped_ratio() -> None:
    project = project_of(todo("a", 6.5), members=[Member("田中", 2.0)])
    assert summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}).supply == 1.5


def test_member_filter_counts_that_members_tasks_and_supply() -> None:
    project = project_of(
        todo("田中の", 6.5, assignees=[Assignee("田中")]),
        todo("鈴木の", 13, assignees=[Assignee("鈴木")]),
        members=[Member("田中", 1.0), Member("鈴木", 0.5)],
    )
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}, "田中")
    assert (backlog.hours, backlog.supply) == (6.5, 1.0)
    assert [row[0] for row in backlog.by_member] == ["田中"]


def test_by_member_splits_shared_tasks_by_allocation_and_lists_the_unassigned() -> None:
    project = project_of(
        todo("共同", 10, assignees=[Assignee("田中", 0.75), Assignee("鈴木", 0.25)]),
        todo("誰も", 4),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
    )
    rows = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}).by_member
    assert rows == [("田中", 7.5), ("鈴木", 2.5), (UNASSIGNED, 4.0)]


def test_summarize_carries_the_backlog() -> None:
    project = project_of(todo("a", 6.5))
    data = summarize(project, WEEK, NOW, {}, PeriodKind.WEEK)
    assert data.backlog.hours == 6.5


def test_member_filter_counts_only_that_members_share_of_a_shared_task() -> None:
    project = project_of(
        todo("共同", 10, assignees=[Assignee("田中", 0.75), Assignee("鈴木", 0.25)]),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
    )
    backlog = summarize_backlog(project, WEEK, PeriodKind.WEEK, NOW, {}, "田中")
    assert backlog.hours == 7.5  # 合計と担当別の棒が食い違わない
    assert backlog.by_member == [("田中", 7.5)]
    assert backlog.required == 7.5 / (6.5 * 3)


def test_a_task_running_past_the_period_counts_only_the_part_up_to_the_period_end() -> None:
    # 金曜 6.5h + 翌月曜 6.5h。今週(〜日曜)に入るのは金曜の半分
    spanning = Task("またぐ", planned_start=datetime(2026, 10, 9, 9), effort_hours=13)
    backlog = summarize_backlog(project_of(spanning), WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.hours == 6.5


def test_a_task_that_started_before_today_keeps_its_past_part() -> None:
    # 月曜に始める予定の未着手。まだ手を付けていないので、月・火の分も残っている
    late = Task("遅れ気味", planned_start=datetime(2026, 10, 5, 9), effort_hours=26)  # 月〜木
    assert summarize_backlog(project_of(late), WEEK, PeriodKind.WEEK, NOW, {}).hours == 26


def test_an_overdue_task_is_counted_in_full() -> None:
    overdue = Task("先月の遅れ", planned_start=datetime(2026, 9, 1, 9), effort_hours=8)
    assert summarize_backlog(project_of(overdue), WEEK, PeriodKind.WEEK, NOW, {}).hours == 8


def test_a_task_without_a_schedule_is_counted_in_a_limited_period() -> None:
    backlog = summarize_backlog(project_of(Task("日程なし", effort_hours=5)), WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.hours == 5


def test_a_task_without_a_schedule_whose_deadline_is_after_the_period_is_left_out() -> None:
    later = Task("来月締切", effort_hours=5, deadline=datetime(2026, 11, 20, 17))
    assert summarize_backlog(project_of(later), WEEK, PeriodKind.WEEK, NOW, {}).hours == 0


def test_a_task_before_a_future_period_but_not_overdue_is_left_out() -> None:
    soon = Task("明日", planned_start=datetime(2026, 10, 8, 9), effort_hours=6.5)
    nov = Period(date(2026, 11, 9), date(2026, 11, 13))
    assert summarize_backlog(project_of(soon), nov, PeriodKind.CUSTOM, NOW, {}).hours == 0


def test_no_workday_left_in_the_period_uses_the_next_workday() -> None:
    # 水・木・金が休みで、今週の稼働日が残っていない。次の稼働日(月曜)の 1 日で終える場合を示す
    holidays = {date(2026, 10, d): "休" for d in (7, 8, 9)}
    backlog = summarize_backlog(project_of(todo("a", 6.5)), WEEK, PeriodKind.WEEK, NOW, holidays)
    assert (backlog.days, backlog.required) == (1, 1.0)


def test_opening_on_a_weekend_uses_the_next_workday_for_this_week() -> None:
    saturday = datetime(2026, 10, 10, 12)
    backlog = summarize_backlog(project_of(todo("a", 6.5)), WEEK, PeriodKind.WEEK, saturday, {})
    assert (backlog.days, backlog.required) == (1, 1.0)


def test_a_period_already_over_gives_zero_days() -> None:
    past = Period(date(2026, 9, 1), date(2026, 9, 30))
    backlog = summarize_backlog(project_of(todo("a", 6.5)), past, PeriodKind.CUSTOM, NOW, {})
    assert backlog.days == 0


def test_the_partial_first_day_is_weighed_by_the_hours_actually_in_the_period() -> None:
    # 金曜 14:00 開始の 13h は、金 1.5h + 月 6.5h + 火 5h。今週(〜日曜)に入るのは金曜の 1.5h だけ
    afternoon = Task("午後開始", planned_start=datetime(2026, 10, 9, 14), effort_hours=13)
    backlog = summarize_backlog(project_of(afternoon), WEEK, PeriodKind.WEEK, NOW, {})
    assert backlog.hours == 1.5


def test_many_tasks_with_a_far_end_are_summed_quickly() -> None:
    from time import perf_counter

    far = [
        Task(f"t{i}", planned_start=datetime(2026, 10, 8, 9), planned_end=datetime(2100, 1, 1, 9),
             planned_end_manual=True, effort_hours=8)
        for i in range(300)
    ]
    started = perf_counter()
    backlog = summarize_backlog(project_of(*far), WEEK, PeriodKind.WEEK, NOW, {})
    assert perf_counter() - started < 5  # 日ごとに回していたころは 20 秒を超えた
    assert backlog.hours > 0


def test_a_task_ending_at_midnight_does_not_reach_into_the_next_day() -> None:
    # 木曜 9:00 から 6.5h → 木曜 15:30 で終わる。1 日だけにかかり、今週の分は全量
    one_day = Task("1日", planned_start=datetime(2026, 10, 8, 9), planned_end=datetime(2026, 10, 9, 0),
                   planned_end_manual=True, effort_hours=6.5)
    assert summarize_backlog(project_of(one_day), WEEK, PeriodKind.WEEK, NOW, {}).hours == 6.5
