"""負荷の調整(rebalance)の計算の確認。"""

from datetime import date, datetime

import pytest

from projectapp.models import (
    Assignee,
    Member,
    Project,
    Status,
    Task,
    TaskKind,
    union_assignees,
)
from projectapp.rebalance import (
    Edit,
    adjustable,
    apply_edits,
    has_varying_rate,
    rate_of,
    rate_text,
    tasks_of,
)

NOW = datetime(2026, 10, 5, 8)


def task(task_id: str, rate: float = 0.6, **kw: object) -> Task:
    return Task(
        task_id.upper(),
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=13,
        assignees=[Assignee("田中", rate)],
        id=task_id,
        **kw,  # type: ignore[arg-type]
    )


def project(*tasks: Task, others: tuple[str, ...] = ("鈴木",)) -> Project:
    members = [Member("田中", 1.0), *(Member(name, 1.0) for name in others)]
    return Project("P", base_date=date(2026, 10, 5), members=members, tasks=list(tasks))


def crew(item: Task) -> list[tuple[str, float]]:
    return [(a.name, a.allocation) for a in item.assignees]


def rows(weeks: list[list[Assignee]]) -> list[list[tuple[str, float]]]:
    return [[(a.name, a.allocation) for a in week] for week in weeks]


def weekly_task() -> Task:
    weekly = [
        [Assignee("田中", 1.0)],
        [Assignee("田中", 0.5), Assignee("鈴木", 1.0)],
    ]
    daily = {
        1: [[Assignee("田中", 0.5), Assignee("鈴木", 1.0)] for _ in range(3)]
        + [[Assignee("鈴木", 1.0)] for _ in range(4)]
    }
    return Task(
        "W",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=40,
        weekly_crew=weekly,
        daily_crew=daily,
        assignees=union_assignees(weekly),
        id="w",
    )


def test_adjustable_needs_a_normal_unfinished_task_the_owner_has() -> None:
    assert adjustable(task("a"), "田中")
    assert not adjustable(task("a"), "鈴木")
    assert not adjustable(task("a", status=Status.DONE), "田中")
    assert not adjustable(task("a", kind=TaskKind.CHECKPOINT), "田中")


def test_tasks_of_lists_only_the_owners_adjustable_tasks_in_order() -> None:
    other = Task("他", assignees=[Assignee("鈴木")], id="o")
    p = project(task("a"), other, task("d", status=Status.DONE), task("b"))
    assert [t.id for t in tasks_of(p, "田中")] == ["a", "b"]


def test_a_rate_edit_sets_the_owners_rate_and_keeps_the_original() -> None:
    p = project(task("a"))
    result = apply_edits(p, "田中", [Edit("a", "rate", rate=0.4)], {}, NOW)
    assert crew(result.task_map()["a"]) == [("田中", 0.4)]
    assert crew(p.task_map()["a"]) == [("田中", 0.6)]


def test_a_move_replaces_the_owner_keeping_the_rate_or_using_the_given_one() -> None:
    p = project(task("a"), task("b"))
    result = apply_edits(
        p,
        "田中",
        [Edit("a", "move", "鈴木"), Edit("b", "move", "鈴木", rate=0.4)],
        {},
        NOW,
    )
    assert crew(result.task_map()["a"]) == [("鈴木", 0.6)]
    assert crew(result.task_map()["b"]) == [("鈴木", 0.4)]


def test_a_move_keeps_the_targets_rate_when_the_target_is_already_there() -> None:
    both = task("a")
    both.assignees = [Assignee("田中", 0.6), Assignee("鈴木", 0.3)]
    result = apply_edits(
        project(both), "田中", [Edit("a", "move", "鈴木", rate=0.9)], {}, NOW
    )
    assert crew(result.task_map()["a"]) == [("鈴木", 0.3)]


def test_an_add_appends_the_target_at_fifty_percent_and_skips_an_existing_one() -> None:
    both = task("b")
    both.assignees = [Assignee("田中", 0.6), Assignee("鈴木", 0.3)]
    p = project(task("a"), both)
    result = apply_edits(
        p, "田中", [Edit("a", "add", "鈴木"), Edit("b", "add", "鈴木")], {}, NOW
    )
    assert crew(result.task_map()["a"]) == [("田中", 0.6), ("鈴木", 0.5)]
    assert crew(result.task_map()["b"]) == [("田中", 0.6), ("鈴木", 0.3)]


@pytest.mark.parametrize(
    "edit",
    [
        Edit("zz", "rate", rate=0.5),  # ないタスク
        Edit("a", "rate"),  # 率がない
        Edit("a", "rate", rate=0.0),
        Edit("a", "rate", rate=1.5),
        Edit("a", "move", "佐藤"),  # メンバーにいない
        Edit("a", "move", "田中"),  # 自分
        Edit("a", "move"),  # 名前がない
        Edit("a", "add", "鈴木", rate=2.0),
        Edit("d", "rate", rate=0.5),  # 終了したタスク
    ],
)
def test_a_bad_edit_is_refused(edit: Edit) -> None:
    p = project(task("a"), task("d", status=Status.DONE))
    with pytest.raises(ValueError):
        apply_edits(p, "田中", [edit], {}, NOW)


def test_the_same_task_cannot_be_edited_twice() -> None:
    p = project(task("a"))
    with pytest.raises(ValueError, match="2 回"):
        apply_edits(
            p,
            "田中",
            [Edit("a", "rate", rate=0.5), Edit("a", "add", "鈴木")],
            {},
            NOW,
        )


def test_the_end_is_reviewed_when_the_rate_changes_after_some_progress() -> None:
    p = project(task("p", progress=50, status=Status.RUNNING), task("a"))
    result = apply_edits(
        p,
        "田中",
        [Edit("p", "rate", rate=0.3), Edit("a", "rate", rate=0.3)],
        {},
        NOW,
    )
    reviewed, plain = result.task_map()["p"], result.task_map()["a"]
    assert reviewed.planned_end is not None and reviewed.planned_end_manual
    assert not plain.planned_end_manual  # 進捗も実績もないタスクは見直さない


def test_a_rate_edit_applies_to_every_week_and_day_the_owner_appears() -> None:
    p = project(weekly_task(), others=("鈴木", "佐藤"))
    new = apply_edits(p, "田中", [Edit("w", "rate", rate=0.3)], {}, NOW).task_map()["w"]
    assert rows(new.weekly_crew) == [
        [("田中", 0.3)],
        [("田中", 0.3), ("鈴木", 1.0)],
    ]
    assert rows(new.daily_crew[1])[:3] == [[("田中", 0.3), ("鈴木", 1.0)]] * 3
    assert rows(new.daily_crew[1])[3:] == [[("鈴木", 1.0)]] * 4  # いない日は変えない
    assert crew(new) == [("田中", 0.3), ("鈴木", 1.0)]


def test_a_move_replaces_the_owner_in_every_week_and_day_and_keeps_the_union() -> None:
    p = project(weekly_task(), others=("鈴木", "佐藤"))
    new = apply_edits(p, "田中", [Edit("w", "move", "佐藤")], {}, NOW).task_map()["w"]
    assert rows(new.weekly_crew) == [
        [("佐藤", 1.0)],
        [("佐藤", 0.5), ("鈴木", 1.0)],
    ]
    assert [[a.name for a in day] for day in new.daily_crew[1]] == (
        [["佐藤", "鈴木"]] * 3 + [["鈴木"]] * 4
    )
    assert sorted(a.name for a in new.assignees) == ["佐藤", "鈴木"]


def test_an_add_appends_in_every_week_the_owner_appears_and_keeps_existing_ones() -> (
    None
):
    p = project(weekly_task(), others=("鈴木", "佐藤"))
    new = apply_edits(p, "田中", [Edit("w", "add", "鈴木")], {}, NOW).task_map()["w"]
    assert rows(new.weekly_crew) == [
        [("田中", 1.0), ("鈴木", 0.5)],  # 鈴木のいなかった週には、50% で足す
        [("田中", 0.5), ("鈴木", 1.0)],  # すでにいる週は変えない
    ]


def test_an_edit_does_not_touch_weeks_where_the_owner_is_absent() -> None:
    weekly = [[Assignee("鈴木", 1.0)], [Assignee("田中", 0.5)]]
    only_second = Task(
        "W",
        planned_start=datetime(2026, 10, 5, 9),
        effort_hours=40,
        weekly_crew=weekly,
        assignees=union_assignees(weekly),
        id="w",
    )
    new = apply_edits(
        project(only_second), "田中", [Edit("w", "rate", rate=0.2)], {}, NOW
    ).task_map()["w"]
    assert rows(new.weekly_crew) == [[("鈴木", 1.0)], [("田中", 0.2)]]


def test_rate_helpers_report_a_single_rate_or_a_range() -> None:
    simple, weekly = task("a"), weekly_task()
    assert rate_of(simple, "田中") == 0.6 and rate_text(simple, "田中") == "60%"
    assert not has_varying_rate(simple, "田中")
    assert rate_of(weekly, "田中") is None
    assert rate_text(weekly, "田中") == "50〜100%"
    assert has_varying_rate(weekly, "田中")
    assert rate_text(simple, "鈴木") == "-"
