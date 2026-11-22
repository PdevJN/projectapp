from projectapp.daily_crew import add_member, remove_member, split_week
from projectapp.models import Assignee, Task


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
