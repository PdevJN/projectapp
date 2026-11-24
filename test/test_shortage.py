from datetime import date, datetime

import pytest

from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from projectapp.shortage import (
    RequiredRate,
    Shortage,
    TrialCompare,
    WeekBurn,
    burn_hint,
    compare_changed,
    compare_hint,
    compare_text,
    compare_trial,
    burn_text,
    due_of,
    required_rate,
    required_rate_hint,
    required_rate_text,
    shortage_gap_text,
    shortage_hint,
    shortage_text,
    task_shortage,
    weekly_burn,
)

MON = datetime(2026, 10, 5, 9)  # 稼働の枠は 9:00〜15:30(6.5h)
FRI = datetime(2026, 10, 9, 17)  # 月〜金の稼働量は 5 日 × 6.5h = 32.5h


def project_of(*tasks: Task) -> Project:
    return Project(
        "P",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0), Member("鈴木", 1.0)],
        sections=[Section("s", list(tasks))],
    )


def task_of(**kwargs) -> Task:
    base = dict(
        planned_start=MON,
        effort_hours=40.0,
        deadline=FRI,
        assignees=[Assignee("田中")],
    )
    return Task("設計", **{**base, **kwargs})


def judged(task: Task, now: datetime = MON) -> Shortage | str:
    return task_shortage(task, project_of(task), {}, now)


def test_the_due_is_the_deadline_then_a_manual_planned_end() -> None:
    manual = datetime(2026, 10, 8, 17)
    assert due_of(task_of()) == (FRI, "締切")
    assert due_of(
        task_of(deadline=None, planned_end=manual, planned_end_manual=True)
    ) == (
        manual,
        "完了予定",
    )
    assert (
        due_of(task_of(deadline=None, planned_end=manual)) is None
    )  # 算出の完了予定は基準にしない
    assert due_of(task_of(deadline=None)) is None


def test_a_shortage_is_the_remaining_effort_minus_the_capacity_to_the_due() -> None:
    value = judged(task_of())
    assert isinstance(value, Shortage)
    assert value.remaining == pytest.approx(40.0)
    assert value.capacity == pytest.approx(32.5)
    assert value.gap == pytest.approx(7.5) and value.kind == "不足"
    assert value.unit == pytest.approx(32.5)
    assert value.people == pytest.approx(7.5 / 32.5)
    assert value.basis == "締切"


def test_a_lower_rate_makes_the_shortage_bigger() -> None:
    value = judged(task_of(assignees=[Assignee("田中", 0.5)]))
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(16.25) and value.gap == pytest.approx(23.75)


def test_more_members_make_a_margin() -> None:
    value = judged(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert isinstance(value, Shortage)
    assert value.gap == pytest.approx(-25.0) and value.kind == "余裕"
    assert value.people == pytest.approx(25.0 / 32.5)  # 絶対値


def test_a_gap_that_rounds_to_zero_is_just_right() -> None:
    value = judged(task_of(effort_hours=32.51))
    assert isinstance(value, Shortage) and value.kind == "ちょうど"
    assert shortage_text(value) == "ちょうど"


def test_progress_reduces_the_remaining_effort() -> None:
    value = judged(task_of(progress=50))
    assert isinstance(value, Shortage)
    assert value.remaining == pytest.approx(20.0) and value.kind == "余裕"


def test_a_task_without_assignees_has_no_capacity_but_the_unit_still_counts() -> None:
    value = judged(task_of(assignees=[]))
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(32.5)  # 担当者なしは換算率 1 の 1 人
    # (pace.py と同じ扱い)


def test_the_weekly_crew_changes_the_capacity() -> None:
    task = task_of(
        weekly_crew=[[Assignee("田中", 0.5)], [Assignee("田中")]],
        deadline=datetime(2026, 10, 16, 17),
    )
    value = judged(task)
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(16.25 + 32.5)


def test_a_future_start_counts_from_the_start() -> None:
    task = task_of(planned_start=datetime(2026, 10, 7, 9))  # 水曜から
    value = judged(task, now=MON)
    assert isinstance(value, Shortage)
    assert value.capacity == pytest.approx(3 * 6.5)


def test_holidays_do_not_count() -> None:
    task = task_of()
    value = task_shortage(task, project_of(task), {date(2026, 10, 7): "休み"}, MON)
    assert isinstance(value, Shortage) and value.capacity == pytest.approx(26.0)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        (task_of(effort_hours=0.0), "工数がありません"),
        (task_of(deadline=None), "基準日"),
        (task_of(planned_start=None), "開始日がありません"),
        (task_of(deadline=datetime(2026, 10, 1, 17)), "基準日を過ぎています"),
        (task_of(progress=100), "残りの工数がありません"),
        (task_of(status=Status.DONE), "終了"),
        (task_of(kind=TaskKind.CHECKPOINT), "通常"),
    ],
)
def test_reasons_when_it_cannot_be_shown(task: Task, reason: str) -> None:
    value = judged(task)
    assert isinstance(value, str) and reason in value


def test_the_text_and_the_hint() -> None:
    value = judged(task_of())
    assert isinstance(value, Shortage)
    assert shortage_text(value) == "あと 7.5h 足りません(約 0.2 人)"
    assert shortage_hint(value) == "残り 40.0h / 稼働 32.5h(10/09 17:00 まで。締切)"
    margin = judged(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert isinstance(margin, Shortage)
    assert shortage_text(margin) == "余裕 25.0h(約 0.8 人)"


def test_a_due_before_the_start_has_its_own_reason() -> None:
    value = judged(task_of(planned_start=datetime(2026, 10, 12, 9)), now=MON)
    assert isinstance(value, str) and "開始より前" in value


def test_a_tiny_gap_does_not_show_zero_people() -> None:
    value = judged(task_of(effort_hours=32.6))
    assert isinstance(value, Shortage)
    assert shortage_text(value) == "あと 0.1h 足りません"


def test_remaining_and_capacity_match_the_warning_pace() -> None:
    from projectapp.pace import pace

    task = task_of(deadline=None, planned_end=FRI, planned_end_manual=True)
    value = judged(task)
    expected = pace(task, project_of(task), {}, MON)
    assert isinstance(value, Shortage) and expected is not None
    assert value.remaining == pytest.approx(expected.remaining)
    assert value.capacity == pytest.approx(expected.capacity)


ORIGIN = date(2026, 10, 5)


def burns(task: Task, now: datetime = MON, weeks: int = 3, holidays=None):
    return weekly_burn(task, project_of(task), holidays or {}, now, weeks, ORIGIN)


def test_the_burn_runs_out_in_the_second_week() -> None:
    value = burns(task_of(deadline=None))
    assert isinstance(value, list) and len(value) == 3
    first, second, third = value
    assert (first.before, first.burn, first.left) == pytest.approx((40.0, 32.5, 7.5))
    assert (second.before, second.burn, second.left) == pytest.approx((7.5, 7.5, 0.0))
    assert second.done and not first.done
    assert (third.before, third.burn, third.left) == (0.0, 0.0, 0.0)
    assert not third.done


def test_the_ranges_are_whole_weeks_from_the_origin() -> None:
    value = burns(task_of(deadline=None))
    assert isinstance(value, list)
    assert value[0].first == MON and value[0].last == datetime(2026, 10, 12)
    assert value[1].first == datetime(2026, 10, 12) and value[1].last == datetime(
        2026, 10, 19
    )


def test_a_lower_rate_stretches_the_burn_over_three_weeks() -> None:
    value = burns(task_of(deadline=None, assignees=[Assignee("田中", 0.5)]))
    assert isinstance(value, list)
    assert [round(w.burn, 2) for w in value] == [16.25, 16.25, 7.5]
    assert [w.done for w in value] == [False, False, True]


def test_the_first_week_counts_from_now_when_now_is_mid_week() -> None:
    value = burns(task_of(deadline=None), now=datetime(2026, 10, 7, 9))  # 水〜金の 3 日
    assert isinstance(value, list)
    assert value[0].first == datetime(2026, 10, 7, 9)
    assert value[0].burn == pytest.approx(19.5) and value[0].left == pytest.approx(20.5)


def test_a_week_already_past_burns_nothing() -> None:
    value = burns(task_of(deadline=None), now=datetime(2026, 10, 14, 9))  # 第 2 週の水
    assert isinstance(value, list)
    assert value[0].burn == 0.0 and value[0].left == pytest.approx(40.0)
    assert value[0].first == value[0].last
    assert value[1].burn == pytest.approx(19.5)


def test_a_start_in_the_future_starts_the_count_there() -> None:
    task = task_of(deadline=None, planned_start=datetime(2026, 10, 7, 9))
    value = weekly_burn(task, project_of(task), {}, MON, 3, date(2026, 10, 7))
    assert isinstance(value, list)
    assert value[0].first == datetime(2026, 10, 7, 9)  # 今ではなく開始から


def test_a_holiday_lowers_that_weeks_burn() -> None:
    value = burns(task_of(deadline=None), holidays={date(2026, 10, 7): "祝"})
    assert isinstance(value, list)
    assert value[0].burn == pytest.approx(26.0)


def test_weekly_crews_change_the_burn_week_by_week() -> None:
    task = task_of(
        deadline=None,
        weekly_crew=[[Assignee("田中", 0.5)], [Assignee("田中")]],
    )
    value = burns(task)
    assert isinstance(value, list)
    assert [round(w.burn, 2) for w in value] == [16.25, 23.75, 0.0]
    assert value[1].done


def test_a_daily_week_counts_each_day_with_its_own_crew() -> None:
    half = [Assignee("田中", 0.5)]
    task = task_of(
        deadline=None,
        weekly_crew=[[Assignee("田中")], [Assignee("田中")]],
        daily_crew={0: [half] * 7},
    )
    value = burns(task)
    assert isinstance(value, list)
    assert value[0].burn == pytest.approx(16.25)


def test_a_crew_without_anyone_counts_as_one_person() -> None:
    value = burns(task_of(deadline=None, assignees=[]))
    assert isinstance(value, list)
    assert value[0].burn == pytest.approx(32.5)


def test_progress_lowers_the_remaining_before_the_first_week() -> None:
    value = burns(task_of(deadline=None, progress=50))
    assert isinstance(value, list)
    assert value[0].before == pytest.approx(20.0)
    assert value[0].done  # 20h は第 1 週の稼働量 32.5h に収まる


def test_no_deadline_is_needed() -> None:
    assert isinstance(burns(task_of(deadline=None, planned_end=None)), list)


def test_the_total_burn_equals_the_capacity_to_the_due() -> None:
    task = task_of(effort_hours=100.0, deadline=datetime(2026, 10, 23, 17))  # 3 週
    short = judged(task)
    value = burns(task)
    assert isinstance(short, Shortage) and isinstance(value, list)
    assert sum(w.burn for w in value) == pytest.approx(short.capacity, abs=6.5 * 2)
    # 最終週の金曜 17:00 は枠の外(15:30 まで)なので、枠の終わりまでの 3 週の稼働量と一致する
    assert sum(w.burn for w in value) == pytest.approx(97.5)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        (task_of(kind=TaskKind.CHECKPOINT), "通常のタスクではありません"),
        (task_of(status=Status.DONE), "終了したタスクです"),
        (task_of(effort_hours=0.0), "工数がありません"),
        (task_of(planned_start=None), "開始日がありません"),
        (task_of(progress=100), "残りの工数がありません"),
    ],
)
def test_burn_reasons(task: Task, reason: str) -> None:
    assert burns(task) == reason


def test_many_weeks_are_cheap() -> None:
    value = burns(task_of(deadline=None, effort_hours=4000.0), weeks=52)
    assert isinstance(value, list) and len(value) == 52


def test_burn_text_shapes() -> None:
    first = WeekBurn(0, MON, datetime(2026, 10, 12), 40.0, 32.5, 7.5)
    last = WeekBurn(1, datetime(2026, 10, 12), datetime(2026, 10, 19), 7.5, 7.5, 0.0)
    after = WeekBurn(2, datetime(2026, 10, 19), datetime(2026, 10, 26), 0.0, 0.0, 0.0)
    assert burn_text(first) == "消化 32.5h / 残り 7.5h"
    assert burn_text(last) == "消化 7.5h / 完了"
    assert burn_text(after) == "—"
    assert burn_text(first, narrow=True) == "32.5h→7.5h"
    assert burn_text(last, narrow=True) == "7.5h 完了"
    assert burn_text(after, narrow=True) == "—"


def test_burn_hint_names_the_week_and_the_change() -> None:
    first = WeekBurn(0, MON, datetime(2026, 10, 12), 40.0, 32.5, 7.5)
    assert burn_hint(first) == "10/05〜10/11 の稼働 32.5h。残り 40.0h → 7.5h"


def needed(task: Task, now: datetime = MON) -> RequiredRate | str:
    return required_rate(task, project_of(task), {}, now)


def rates(value: RequiredRate) -> dict[str, tuple[float, float]]:
    return {name: (now_rate, need) for name, now_rate, need in value.members}


def test_a_shortage_that_reaches_scales_everyone_by_the_same_factor() -> None:
    task = task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)])
    value = needed(task)  # 残り 40h・稼働 32.5h
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(40 / 32.5, rel=1e-4)
    assert rates(value)["田中"][1] == pytest.approx(0.5 * 40 / 32.5, rel=1e-4)
    assert rates(value)["鈴木"] == pytest.approx((0.5, 0.5 * 40 / 32.5), rel=1e-4)
    assert value.short_hours == 0.0 and value.short_people is None


def test_a_member_already_at_100_percent_stays_and_the_others_make_up_the_rest() -> (
    None
):
    task = task_of(
        effort_hours=60.0, assignees=[Assignee("田中"), Assignee("鈴木", 0.5)]
    )  # 稼働 32.5 + 16.25 = 48.75h。田中は 100% のまま、鈴木が 0.846 まで
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(1.6923, rel=1e-3)
    assert rates(value)["田中"] == pytest.approx((1.0, 1.0))
    assert rates(value)["鈴木"] == pytest.approx((0.5, 0.8462), rel=1e-3)


def test_when_even_everyone_at_100_percent_falls_short_there_is_no_factor() -> None:
    value = needed(task_of())  # 田中 100%・残り 40h・稼働 32.5h
    assert isinstance(value, RequiredRate)
    assert value.factor is None and value.members == ()
    assert value.short_hours == pytest.approx(7.5)
    assert value.short_people == pytest.approx(7.5 / 32.5)


def test_weekly_crews_are_scaled_in_every_week() -> None:
    task = task_of(
        effort_hours=30.0,
        assignees=[Assignee("田中", 0.5)],
        weekly_crew=[[Assignee("田中", 0.5)]],
    )  # 稼働 16.25h
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(30 / 16.25, rel=1e-4)


def test_daily_crews_use_the_peak_rate_for_the_member() -> None:
    days = [[Assignee("田中", 0.5)] for _ in range(3)] + [
        [Assignee("田中")] for _ in range(4)
    ]  # 月〜水 50%・木〜日 100%。稼働 9.75 + 13 = 22.75h
    task = task_of(
        effort_hours=30.0,
        assignees=[Assignee("田中")],
        weekly_crew=[[Assignee("田中")]],
        daily_crew={0: days},
    )
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert value.factor == pytest.approx(1.7436, rel=1e-3)
    assert rates(value)["田中"] == pytest.approx((1.0, 1.0))


def test_the_original_task_is_not_changed() -> None:
    task = task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)])
    needed(task)
    assert [a.allocation for a in task.assignees] == [0.5, 0.5]


def test_no_shortage_or_no_due_gives_a_reason_string() -> None:
    assert needed(task_of(effort_hours=20.0)) == "不足していません"
    reason = needed(task_of(deadline=None))
    assert isinstance(reason, str) and "基準日" in reason
    assert needed(task_of(), now=datetime(2026, 10, 12, 9)) == "基準日を過ぎています"


def test_the_text_names_the_factor_and_each_members_rate() -> None:
    task = task_of(
        effort_hours=60.0, assignees=[Assignee("田中"), Assignee("鈴木", 0.5)]
    )
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert required_rate_text(value) == "必要な率: 今の ×1.7(田中 100%・鈴木 50→85%)"


def test_the_text_lists_three_members_and_counts_the_rest() -> None:
    members = tuple((f"m{i}", 0.5, 0.6) for i in range(5))
    shortage = Shortage(40.0, 32.5, 32.5, FRI, "締切")
    value = RequiredRate(1.2, members, 0.0, None, shortage)
    assert (
        required_rate_text(value)
        == "必要な率: 今の ×1.2(m0 50→60%・m1 50→60%・m2 50→60%・ほか 2 人)"
    )


def test_the_text_when_even_everyone_at_100_percent_falls_short() -> None:
    value = needed(task_of())
    assert isinstance(value, RequiredRate)
    assert required_rate_text(value) == "全員 100% でもあと 7.5h 足りません(約 0.2 人)"


def test_the_hint_gives_the_remaining_the_capacity_and_the_due() -> None:
    value = needed(task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)]))
    assert isinstance(value, RequiredRate)
    hint = required_rate_hint(value)
    assert "残り 40.0h / 稼働 32.5h" in hint and "10/09 17:00 まで。締切" in hint
    assert "×1.23" in hint


def test_a_52_week_task_with_the_lowest_rate_is_fast() -> None:
    import time

    task = task_of(
        effort_hours=400.0,
        deadline=datetime(2027, 10, 1, 17),
        assignees=[Assignee("田中", 0.01)],
    )
    began = time.perf_counter()
    needed(task)
    assert time.perf_counter() - began < 2.0


def test_a_name_missing_from_the_member_table_is_not_listed() -> None:
    task = task_of(
        effort_hours=30.0, assignees=[Assignee("田中", 0.5), Assignee("外", 0.01)]
    )  # 「外」はメンバー表にいない(稼働に寄与しない)
    value = needed(task)
    assert isinstance(value, RequiredRate)
    assert [name for name, _, _ in value.members] == ["田中"]
    assert "外" not in required_rate_text(value)
    assert value.factor == pytest.approx(30 / 16.25, rel=1e-4)


def test_the_hint_says_the_member_rate_is_the_peak() -> None:
    value = needed(task_of(assignees=[Assignee("田中", 0.5), Assignee("鈴木", 0.5)]))
    assert isinstance(value, RequiredRate)
    assert "最大の率" in required_rate_hint(value)


def compared(before: Task, after: Task, now: datetime = MON) -> TrialCompare:
    return compare_trial(before, project_of(before), after, project_of(after), {}, now)


def test_the_gap_text_is_short_and_has_no_head_count() -> None:
    assert (
        shortage_gap_text(Shortage(40.0, 32.5, 32.5, FRI, "締切")) == "あと 7.5h 不足"
    )
    assert shortage_gap_text(Shortage(30.0, 32.5, 32.5, FRI, "締切")) == "余裕 2.5h"
    assert shortage_gap_text(Shortage(32.5, 32.5, 32.5, FRI, "締切")) == "ちょうど"


def test_adding_a_member_moves_the_end_earlier_and_turns_a_shortage_into_room() -> None:
    value = compared(task_of(), task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    assert compare_changed(value)
    assert compare_text(value) == (
        "前→後: 完了予定 10/13 → 10/08(5 日早まる)・あと 7.5h 不足 → 余裕 25.0h"
    )


def test_removing_a_member_moves_the_end_later() -> None:
    value = compared(task_of(assignees=[Assignee("田中"), Assignee("鈴木")]), task_of())
    assert compare_text(value) == (
        "前→後: 完了予定 10/08 → 10/13(5 日遅れる)・余裕 25.0h → あと 7.5h 不足"
    )


def test_a_smaller_change_shows_the_days_and_the_new_room() -> None:
    value = compared(
        task_of(), task_of(assignees=[Assignee("田中"), Assignee("鈴木", 0.5)])
    )
    assert compare_text(value) == (
        "前→後: 完了予定 10/13 → 10/09(4 日早まる)・あと 7.5h 不足 → 余裕 8.8h"
    )


def test_identical_tasks_show_nothing() -> None:
    value = compared(task_of(), task_of())
    assert not compare_changed(value) and compare_text(value) == ""


def test_a_manual_end_stays_and_only_the_shortage_changes() -> None:
    manual = datetime(2026, 10, 12, 17)
    value = compared(
        task_of(planned_end=manual, planned_end_manual=True),
        task_of(
            planned_end=manual,
            planned_end_manual=True,
            assignees=[Assignee("田中"), Assignee("鈴木")],
        ),
    )
    assert compare_text(value) == "前→後: あと 7.5h 不足 → 余裕 25.0h"


def test_without_a_due_only_the_end_is_compared() -> None:
    value = compared(
        task_of(deadline=None),
        task_of(deadline=None, assignees=[Assignee("田中"), Assignee("鈴木")]),
    )
    assert value.before is None and value.after is None
    assert compare_text(value) == "前→後: 完了予定 10/13 → 10/08(5 日早まる)"


def test_the_same_date_with_a_different_time_is_not_a_change() -> None:
    before = task_of(deadline=None)
    after = task_of(deadline=None, assignees=[Assignee("田中"), Assignee("鈴木", 0.01)])
    value = compared(before, after)
    assert value.before_end is not None and value.after_end is not None
    assert value.before_end != value.after_end
    assert value.before_end.date() == value.after_end.date()
    assert not compare_changed(value) and compare_text(value) == ""


def test_the_hint_gives_the_before_and_after_basis() -> None:
    value = compared(task_of(), task_of(assignees=[Assignee("田中"), Assignee("鈴木")]))
    hint = compare_hint(value)
    assert "前: 残り 40.0h / 稼働 32.5h" in hint
    assert "後: 残り 40.0h / 稼働 65.0h" in hint


def test_comparing_does_not_change_the_tasks() -> None:
    before = task_of()
    after = task_of(assignees=[Assignee("田中"), Assignee("鈴木")])
    compared(before, after)
    assert [a.name for a in before.assignees] == ["田中"]
    assert [a.name for a in after.assignees] == ["田中", "鈴木"]
