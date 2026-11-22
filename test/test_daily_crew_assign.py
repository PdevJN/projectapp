from datetime import datetime

from projectapp.daily_crew import (
    add_member,
    add_member_range,
    cell_in_range,
    ordered_cells,
    range_cells,
    to_weekly,
    current_allocation,
    remove_member,
    set_allocation,
    set_allocation_all,
    split_week,
)
from projectapp.models import Assignee, Member, Project, Task, TaskKind
from projectapp.timeline import effective_end


def task(*names: str) -> Task:
    return Task("t", id="a", assignees=[Assignee(n) for n in names])


def names(crew: list[Assignee]) -> list[str]:
    return [a.name for a in crew]


def test_adding_to_a_plain_task_splits_it_into_weeks_and_adds_only_to_that_week() -> (
    None
):
    result = add_member(task("田中"), "鈴木", 2, weeks=4)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中"],
        ["田中"],
        ["田中", "鈴木"],
        ["田中"],
    ]
    assert names(result.assignees) == ["田中", "鈴木"]  # 和集合


def test_adding_to_a_task_without_assignees_makes_the_whole_task_assigned() -> None:
    result = add_member(task(), "鈴木", 1, weeks=3)
    assert result is not None
    assert result.weekly_crew == [] and names(result.assignees) == ["鈴木"]


def test_the_second_drop_on_an_unassigned_task_is_per_week() -> None:
    first = add_member(task(), "鈴木", 0, weeks=3)
    assert first is not None
    second = add_member(first, "田中", 1, weeks=3)
    assert second is not None
    assert [names(w) for w in second.weekly_crew] == [
        ["鈴木"],
        ["鈴木", "田中"],
        ["鈴木"],
    ]


def test_a_week_beyond_the_defined_ones_is_filled_with_the_last_crew() -> None:
    weekly = add_member(task("田中"), "鈴木", 0, weeks=2)
    assert weekly is not None
    result = add_member(weekly, "佐藤", 4)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中", "鈴木"],
        ["田中"],
        ["田中"],
        ["田中"],
        ["田中", "佐藤"],
    ]


def test_adding_a_duplicate_or_beyond_the_limit_is_rejected() -> None:
    assert add_member(task("田中"), "田中", 0, weeks=2) is None
    assert add_member(task("田中"), "鈴木", 52, weeks=2) is None
    assert add_member(task("田中"), "鈴木", -1, weeks=2) is None


def test_adding_to_a_daily_week_targets_one_day_or_all_days() -> None:
    weekly = add_member(task("田中"), "鈴木", 5, weeks=1)  # 6 週にする
    assert weekly is not None
    daily = split_week(weekly, 1)
    assert daily is not None
    one = add_member(daily, "佐藤", 1, 3)
    assert one is not None
    assert [names(d) for d in one.daily_crew[1]] == [
        ["田中"],
        ["田中"],
        ["田中"],
        ["田中", "佐藤"],
        ["田中"],
        ["田中"],
        ["田中"],
    ]
    every = add_member(daily, "佐藤", 1)
    assert every is not None
    assert all(names(d) == ["田中", "佐藤"] for d in every.daily_crew[1])
    assert names(every.weekly_crew[1]) == ["田中", "佐藤"]  # 週の担当は 7 日の和集合


def test_removing_a_member_from_a_week() -> None:
    added = add_member(task("田中"), "鈴木", 1, weeks=3)
    assert added is not None
    result = remove_member(added, "鈴木", 1)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [["田中"], ["田中"], ["田中"]]


def test_the_last_member_of_a_cell_cannot_be_removed() -> None:
    added = add_member(task("田中"), "鈴木", 1, weeks=3)
    assert added is not None
    assert remove_member(added, "田中", 0) is None  # 週 0 の最後の 1 人
    assert remove_member(task("田中"), "田中", 0) is None  # 週ごとでないタスク
    assert remove_member(added, "佐藤", 1) is None  # いない人


def test_removing_from_all_days_changes_nothing_when_one_day_would_be_empty() -> None:
    weekly = add_member(task("田中"), "鈴木", 1, weeks=2)
    assert weekly is not None
    daily = split_week(weekly, 1)
    assert daily is not None
    one_day = add_member(daily, "佐藤", 1, 2)  # 3 日目だけ佐藤を足す(田中・鈴木・佐藤)
    assert one_day is not None
    # 田中と鈴木は 7 日すべてにいる。どの日も 2 人以上なので、鈴木を全日から外せる
    result = remove_member(one_day, "鈴木", 1)
    assert result is not None and all(
        "鈴木" not in names(d) for d in result.daily_crew[1]
    )
    only = remove_member(
        result, "田中", 1
    )  # 3 日目は田中・佐藤だが、ほかの日は田中だけなので外せない
    assert only is None


def test_removing_from_a_plain_task_splits_it_into_weeks_first() -> None:
    result = remove_member(task("田中", "鈴木"), "鈴木", 1, weeks=3)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中", "鈴木"],
        ["田中"],
        ["田中", "鈴木"],
    ]


def test_removing_from_a_week_beyond_the_defined_ones_fills_the_gap_first() -> None:
    weekly = add_member(task("田中", "鈴木"), "佐藤", 0, weeks=2)
    assert weekly is not None
    result = remove_member(weekly, "鈴木", 3)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中", "鈴木", "佐藤"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
        ["田中"],
    ]


def test_to_weekly_copies_the_crew_to_every_week() -> None:
    from projectapp.daily_crew import to_weekly

    result = to_weekly(task("田中"), 3)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [["田中"]] * 3
    assert to_weekly(result, 3) is None  # すでに週ごと
    assert to_weekly(task(), 3) is None  # 担当者がいない


def rates(crew: list[Assignee]) -> dict[str, float]:
    return {a.name: a.allocation for a in crew}


def test_setting_a_rate_on_a_plain_task_splits_it_and_changes_only_that_week() -> None:
    result = set_allocation(task("田中", "鈴木"), "鈴木", 0.6, 1, weeks=3)
    assert result is not None
    assert [rates(w) for w in result.weekly_crew] == [
        {"田中": 1.0, "鈴木": 1.0},
        {"田中": 1.0, "鈴木": 0.6},
        {"田中": 1.0, "鈴木": 1.0},
    ]
    assert rates(result.assignees) == {"田中": 1.0, "鈴木": 1.0}  # 和集合は大きいほう


def test_setting_a_rate_does_not_change_the_input() -> None:
    original = task("田中")
    set_allocation(original, "田中", 0.5, 0, weeks=2)
    assert original.weekly_crew == [] and original.assignees[0].allocation == 1.0


def test_setting_a_rate_in_a_weekly_task() -> None:
    base = add_member(task("田中"), "鈴木", 1, weeks=2)
    assert base is not None
    result = set_allocation(base, "鈴木", 0.25, 1)
    assert result is not None
    assert rates(result.weekly_crew[1]) == {"田中": 1.0, "鈴木": 0.25}
    assert rates(result.weekly_crew[0]) == {"田中": 1.0}


def test_setting_a_rate_in_a_daily_week_changes_that_day_or_all_days() -> None:
    weekly = set_allocation(task("田中"), "田中", 1.0, 0, weeks=1)  # 同じ値は None
    assert weekly is None
    base = add_member(task("田中"), "鈴木", 0, weeks=2)
    assert base is not None
    split = split_week(base, 0)
    assert split is not None
    one_day = set_allocation(split, "鈴木", 0.5, 0, 3)
    assert one_day is not None
    assert rates(one_day.daily_crew[0][3]) == {"田中": 1.0, "鈴木": 0.5}
    assert rates(one_day.daily_crew[0][2]) == {"田中": 1.0, "鈴木": 1.0}
    assert rates(one_day.weekly_crew[0]) == {"田中": 1.0, "鈴木": 1.0}  # 大きいほう
    all_days = set_allocation(split, "鈴木", 0.5, 0)
    assert all_days is not None
    assert all(rates(d)["鈴木"] == 0.5 for d in all_days.daily_crew[0])
    assert rates(all_days.weekly_crew[0]) == {"田中": 1.0, "鈴木": 0.5}


def test_setting_a_rate_beyond_the_defined_weeks_fills_with_the_tail() -> None:
    base = add_member(task("田中"), "鈴木", 0, weeks=1)
    assert base is not None
    result = set_allocation(base, "田中", 0.5, 3)
    assert result is not None
    assert len(result.weekly_crew) == 4
    assert rates(result.weekly_crew[3]) == {"田中": 0.5, "鈴木": 1.0}
    assert rates(result.weekly_crew[2]) == {"田中": 1.0, "鈴木": 1.0}


def test_setting_a_rate_refuses_what_it_cannot_do() -> None:
    plain = task("田中")
    assert set_allocation(plain, "鈴木", 0.5, 0) is None  # そのセルにいない
    assert set_allocation(plain, "田中", 0.5, 0, 2) is None  # 日ごとでない週に day
    assert set_allocation(plain, "田中", 0.5, 52) is None  # MAX_WEEKS 以上
    assert set_allocation(plain, "田中", 0.5, -1) is None
    assert set_allocation(task(), "田中", 0.5, 0) is None  # 担当者がいない
    summary = Task("s", id="s", kind=TaskKind.SUMMARY, assignees=[Assignee("田中")])
    assert set_allocation(summary, "田中", 0.5, 0) is None


def test_setting_a_rate_refuses_values_outside_the_range() -> None:
    for value in (0.0, 0.009, 1.01, -0.5, float("nan"), float("inf")):
        assert set_allocation(task("田中"), "田中", value, 0) is None
    assert set_allocation(task("田中"), "田中", 0.01, 0, weeks=1) is not None
    assert set_allocation(task("田中"), "田中", 0.5, 0, weeks=1) is not None


def test_current_allocation_reads_the_cell() -> None:
    base = add_member(task("田中"), "鈴木", 1, weeks=3)
    assert base is not None
    base = set_allocation(base, "鈴木", 0.4, 1)
    assert base is not None
    assert current_allocation(base, "鈴木", 1) == 0.4
    assert current_allocation(base, "鈴木", 0) is None  # その週にいない
    assert current_allocation(base, "田中", 5) == 1.0  # 先の週は直前の担当
    assert current_allocation(task("田中"), "田中", 2) == 1.0  # 週ごとでない
    assert current_allocation(base, "田中", 1, 2) is None  # 日ごとでない週に day
    assert current_allocation(base, "田中", 99) is None


def test_set_allocation_all_changes_every_week_and_day_of_that_member() -> None:
    base = add_member(task("田中"), "鈴木", 0, weeks=3)
    assert base is not None
    base = add_member(base, "鈴木", 2)
    assert base is not None
    base = split_week(base, 0)
    assert base is not None
    result = set_allocation_all(base, "鈴木", 0.5)
    assert result is not None
    assert all(rates(d)["鈴木"] == 0.5 for d in result.daily_crew[0])
    assert rates(result.weekly_crew[0]) == {"田中": 1.0, "鈴木": 0.5}
    assert "鈴木" not in rates(result.weekly_crew[1])  # いない週には足さない
    assert rates(result.weekly_crew[2]) == {"田中": 1.0, "鈴木": 0.5}
    assert rates(result.assignees) == {"田中": 1.0, "鈴木": 0.5}


def test_set_allocation_all_on_a_plain_task_keeps_it_plain() -> None:
    result = set_allocation_all(task("田中", "鈴木"), "鈴木", 0.5)
    assert result is not None
    assert result.weekly_crew == [] and rates(result.assignees) == {
        "田中": 1.0,
        "鈴木": 0.5,
    }


def test_set_allocation_all_returns_none_when_nothing_changes() -> None:
    assert set_allocation_all(task("田中"), "田中", 1.0) is None  # 同じ値
    assert set_allocation_all(task("田中"), "鈴木", 0.5) is None  # いない
    assert set_allocation_all(task("田中"), "田中", 0.0) is None  # 範囲外
    assert set_allocation_all(task("田中"), "田中", float("nan")) is None


def test_lowering_the_rate_moves_the_forecast_end_later() -> None:
    def build(rate: float) -> tuple[Project, Task]:
        item = Task(
            "t",
            id="a",
            planned_start=datetime(2026, 11, 16, 9),
            effort_hours=40,
            assignees=[Assignee("田中", rate)],
        )
        return Project("p", members=[Member("田中", 1.0)], tasks=[item]), item

    project, full = build(1.0)
    half = set_allocation(full, "田中", 0.5, 0, weeks=1)
    assert half is not None
    fast = effective_end(full, project, {})
    slow = effective_end(half, Project("p", members=project.members, tasks=[half]), {})
    assert fast is not None and slow is not None and slow > fast


def test_a_range_adds_the_member_to_every_week_in_it() -> None:
    result = add_member_range(task("田中"), "鈴木", (1, None), (2, None), weeks=4)
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中"],
        ["田中", "鈴木"],
        ["田中", "鈴木"],
        ["田中"],
    ]
    assert names(result.assignees) == ["田中", "鈴木"]


def test_a_range_is_the_same_when_first_and_last_are_swapped() -> None:
    forward = add_member_range(task("田中"), "鈴木", (1, None), (2, None), weeks=4)
    backward = add_member_range(task("田中"), "鈴木", (2, None), (1, None), weeks=4)
    assert forward is not None and forward == backward


def test_a_range_skips_cells_that_already_have_the_member() -> None:
    base = add_member(task("田中"), "鈴木", 1, weeks=4)
    assert base is not None
    result = add_member_range(base, "鈴木", (0, None), (2, None))
    assert result is not None
    assert [names(w) for w in result.weekly_crew] == [
        ["田中", "鈴木"],
        ["田中", "鈴木"],  # 重複しない
        ["田中", "鈴木"],
        ["田中"],
    ]


def test_a_range_returns_none_when_every_cell_already_has_the_member() -> None:
    base = add_member_range(task("田中"), "鈴木", (0, None), (2, None), weeks=3)
    assert base is not None
    assert add_member_range(base, "鈴木", (0, None), (2, None)) is None


def test_a_range_across_a_daily_week_adds_only_the_days_in_it() -> None:
    weekly = to_weekly(task("田中"), 3)
    assert weekly is not None
    base = split_week(weekly, 1)
    assert base is not None
    result = add_member_range(base, "鈴木", (0, None), (1, 2))
    assert result is not None
    assert "鈴木" in names(result.weekly_crew[0])
    days = result.daily_crew[1]
    assert ["鈴木" in names(d) for d in days] == [True, True, True] + [False] * 4
    assert "鈴木" in names(result.weekly_crew[1])  # 日の和集合
    assert "鈴木" not in names(result.weekly_crew[2])


def test_a_range_can_start_in_the_middle_of_a_daily_week() -> None:
    weekly = to_weekly(task("田中"), 3)
    assert weekly is not None
    base = split_week(weekly, 1)
    assert base is not None
    result = add_member_range(base, "鈴木", (1, 4), (2, None))
    assert result is not None
    assert ["鈴木" in names(d) for d in result.daily_crew[1]] == [False] * 4 + [
        True
    ] * 3
    assert "鈴木" in names(result.weekly_crew[2])


def test_a_range_beyond_the_defined_weeks_fills_with_the_tail() -> None:
    result = add_member_range(task("田中"), "鈴木", (2, None), (4, None), weeks=1)
    assert result is not None
    # 定義済みの週より先は直前の担当で埋める。最後の週(2)の担当は以降も続くので、週 3・4 は増やさなくても鈴木が入る
    assert [names(w) for w in result.weekly_crew] == [
        ["田中"],
        ["田中"],
        ["田中", "鈴木"],
    ]


def test_a_range_on_an_unassigned_task_makes_the_whole_task_assigned() -> None:
    result = add_member_range(task(), "鈴木", (0, None), (2, None), weeks=3)
    assert result is not None
    assert result.weekly_crew == [] and names(result.assignees) == ["鈴木"]


def test_a_range_refuses_what_it_cannot_do() -> None:
    assert add_member_range(task("田中"), "鈴木", (0, None), (52, None)) is None
    assert add_member_range(task("田中"), "鈴木", (-1, None), (1, None)) is None
    summary = Task("s", id="s", kind=TaskKind.SUMMARY, assignees=[Assignee("田中")])
    assert add_member_range(summary, "鈴木", (0, None), (1, None)) is None


def test_cell_in_range_follows_week_and_day_boundaries() -> None:
    assert cell_in_range((1, None), (2, None), 1, None)
    assert cell_in_range((1, None), (2, None), 2, 5)  # 日ごとの週の日も週の範囲に入る
    assert not cell_in_range((1, None), (2, None), 0, None)
    assert not cell_in_range((1, None), (2, None), 3, None)
    assert cell_in_range((1, 2), (3, 4), 1, 2) and not cell_in_range(
        (1, 2), (3, 4), 1, 1
    )
    assert cell_in_range((1, 2), (3, 4), 3, 4) and not cell_in_range(
        (1, 2), (3, 4), 3, 5
    )
    assert cell_in_range((3, 4), (1, 2), 2, None)  # 逆順でも同じ


def test_ordered_cells_and_range_cells() -> None:
    assert ordered_cells((3, 4), (1, None)) == ((1, None), (3, 4))
    daily = {1: [[] for _ in range(7)]}
    assert range_cells(daily, (0, None), (1, 2)) == [(0, None), (1, 0), (1, 1), (1, 2)]
    assert range_cells(daily, (1, 5), (2, None)) == [(1, 5), (1, 6), (2, None)]
