from datetime import date, datetime

from projectapp.assign_trial import (
    apply_trial,
    is_assignable,
    is_dirty,
    start_trial,
    trial_project,
)
from projectapp.models import (
    Assignee,
    Member,
    Project,
    Section,
    Status,
    Task,
    TaskKind,
)


def project() -> Project:
    return Project(
        "demo",
        base_date=date(2026, 10, 5),
        members=[Member("田中", 1.0)],
        sections=[Section("開発", [Task("設計", id="a", effort_hours=8.0)])],
        tasks=[Task("直下", id="t")],
    )


def test_start_trial_copies_the_task() -> None:
    task = Task("設計", id="a")
    trial = start_trial(task)
    assert trial.task == task and trial.task is not task
    assert trial.original is not trial.task


def test_is_dirty_only_when_the_copy_differs() -> None:
    trial = start_trial(Task("設計", id="a"))
    assert is_dirty(trial) is False
    trial.task.assignees = [Assignee("田中")]
    assert is_dirty(trial) is True


def test_is_assignable_excludes_non_normal_and_done_tasks() -> None:
    assert is_assignable(Task("通常", id="a")) is True
    assert is_assignable(Task("実行中", id="b", status=Status.RUNNING)) is True
    assert is_assignable(Task("終了", id="c", status=Status.DONE)) is False
    for kind in (TaskKind.CHECKPOINT, TaskKind.REFERENCE, TaskKind.SUMMARY):
        assert is_assignable(Task("x", id="d", kind=kind)) is False


def test_trial_project_holds_only_the_one_task_and_keeps_the_original_project() -> None:
    base = project()
    trial = start_trial(base.task_map()["a"])
    copy = trial_project(base, trial)
    assert [t.id for t in copy.all_tasks()] == ["a"]
    assert copy.members == base.members and copy.base_date == base.base_date
    assert sorted(t.id for t in base.all_tasks()) == ["a", "t"]  # 元は変えない


def test_apply_trial_writes_the_copy_back_to_the_same_task() -> None:
    base = project()
    trial = start_trial(base.task_map()["a"])
    trial.task.name = "詳細設計"
    assert apply_trial(base, trial) is True
    assert base.task_map()["a"].name == "詳細設計"


def test_apply_trial_returns_false_when_the_task_is_gone() -> None:
    base = project()
    trial = start_trial(base.task_map()["a"])
    base.sections[0].tasks.clear()
    assert apply_trial(base, trial) is False


def test_trial_project_keeps_predecessors_so_the_schedule_matches_the_main_chart() -> (
    None
):
    from projectapp.assign_trial import hidden_ids
    from projectapp.timeline import Schedule

    first = Task(
        "先行", id="a", planned_start=datetime(2026, 11, 16, 9), effort_hours=16
    )
    second = Task("後続", id="b", effort_hours=8, predecessors=["a"])
    base = Project(
        "p", base_date=date(2026, 11, 16), sections=[Section("s", [first, second])]
    )
    trial = start_trial(base.task_map()["b"])
    copy = trial_project(base, trial)
    full = Schedule(base, {})
    part = Schedule(copy, {})
    mine = copy.task_map()["b"]
    assert (part.start(mine), part.end(mine)) == (full.start(second), full.end(second))
    assert hidden_ids(base, trial) == frozenset(
        {"a"}
    )  # 先行は日程のために持つだけで、描かない
