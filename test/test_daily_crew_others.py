from datetime import date, datetime

from projectapp.arrange import copy_task
from projectapp.bulk_edit import BulkChanges, CrewChange, CrewMode, apply_bulk
from projectapp.decompose import Part, decompose, settle
from projectapp.forms import build_task
from projectapp.handoff import _estimate_hours
from projectapp.merge import THEIRS, merge_projects
from projectapp.models import (
    Assignee,
    Member,
    Priority,
    Project,
    Status,
    Task,
    TaskKind,
)
from projectapp.plantuml import weekly_crew_notice

T = [Assignee("田中")]
TS = [Assignee("田中"), Assignee("鈴木")]
DAYS = [list(T)] * 3 + [list(TS)] * 4
START = datetime(2026, 11, 2, 9)  # 月曜


def names(crew):
    return [a.name for a in crew]


def daily_task(**changes: object) -> Task:
    task = Task(
        "a",
        id="ta",
        planned_start=START,
        effort_hours=20.0,
        assignees=[Assignee(a.name) for a in TS],
        weekly_crew=[[Assignee(a.name) for a in TS], [Assignee("田中")]],
        daily_crew={0: [[Assignee(a.name) for a in d] for d in DAYS]},
    )
    for key, value in changes.items():
        setattr(task, key, value)
    return task


def project_of(*tasks: Task, members=None) -> Project:
    return Project(
        name="p",
        base_date=START,
        members=members or [Member("田中", id="m1"), Member("鈴木", id="m2")],
        tasks=list(tasks),
    )


def applied(task: Task, mode: CrewMode, *who: Assignee) -> Task:
    project = project_of(task)
    result = apply_bulk(
        project, [task.id], BulkChanges(crew=CrewChange(mode, tuple(who))), {}
    )
    return result.tasks[task.id]


def test_bulk_add_puts_the_person_into_every_day_and_keeps_the_union() -> None:
    new = applied(daily_task(), CrewMode.ADD, Assignee("佐藤"))
    assert all("佐藤" in names(d) for d in new.daily_crew[0])
    assert names(new.weekly_crew[0]) == ["田中", "鈴木", "佐藤"]


def test_bulk_remove_leaves_the_days_and_fills_the_emptied_ones() -> None:
    task = daily_task()
    task.daily_crew[0] = [[Assignee("鈴木")]] * 3 + [
        [Assignee("田中"), Assignee("鈴木")]
    ] * 4
    new = applied(task, CrewMode.REMOVE, Assignee("鈴木"))
    # 外して空になった日は、その週の(外した後の)担当で埋まる
    assert [names(d) for d in new.daily_crew[0]] == [["田中"]] * 7
    assert names(new.weekly_crew[0]) == ["田中"]


def test_bulk_remove_of_everyone_ends_weekly_and_daily() -> None:
    task = daily_task()
    task.weekly_crew = [[Assignee("田中")], [Assignee("田中")]]
    task.daily_crew = {0: [[Assignee("田中")] for _ in range(7)]}
    new = applied(task, CrewMode.REMOVE, Assignee("田中"))
    assert new.weekly_crew == [] and new.daily_crew == {} and new.assignees == []


def test_bulk_replace_drops_the_daily_weeks() -> None:
    new = applied(daily_task(), CrewMode.REPLACE, Assignee("佐藤"))
    assert new.daily_crew == {} and new.weekly_crew == []
    assert names(new.assignees) == ["佐藤"]


def test_merge_takes_a_daily_change_made_by_one_side_only() -> None:
    base = project_of(daily_task())
    changed = daily_task()
    changed.daily_crew[0][5] = [Assignee("鈴木")]
    result = merge_projects(base, base, project_of(changed))
    assert result.conflicts == []
    assert names(result.project.tasks[0].daily_crew[0][5]) == ["鈴木"]


def test_merge_reports_one_conflict_when_both_edit_the_same_week() -> None:
    base = project_of(daily_task())
    ours, theirs = daily_task(), daily_task()
    ours.daily_crew[0][1] = [Assignee("鈴木")]
    theirs.daily_crew[0][2] = [Assignee("鈴木")]
    result = merge_projects(base, project_of(ours), project_of(theirs))
    assert [c.field for c in result.conflicts] == ["日ごとの担当"]
    assert any("第1週(日ごと)" in str(c.theirs) for c in result.conflicts)
    chosen = merge_projects(
        base, project_of(ours), project_of(theirs), {result.conflicts[0].id: THEIRS}
    ).project.tasks[0]
    assert names(chosen.daily_crew[0][2]) == ["鈴木"]


def test_merge_removes_a_deleted_member_from_the_days_and_fills_empty_days() -> None:
    task = daily_task()
    task.daily_crew[0][0] = [Assignee("鈴木")]
    base = project_of(task)
    theirs = project_of(task, members=[Member("田中", id="m1")])
    result = merge_projects(base, base, theirs)
    merged = result.project.tasks[0]
    assert names(merged.daily_crew[0][0]) == ["田中"]  # 空になった日は週の担当で埋まる
    assert all("鈴木" not in names(d) for d in merged.daily_crew[0])
    assert any("日ごとの担当から外しました" in n for n in result.notes)


def test_decompose_reads_todays_crew_from_the_daily_week_and_clears_the_parent() -> (
    None
):
    task = daily_task(progress=10)
    project = project_of(task)
    today = datetime(2026, 11, 5, 10)  # 第 1 週の 4 日目(鈴木が加わる日)
    settled = settle(project, task, {}, today)
    assert settled is not None and names(settled.crew) == ["田中", "鈴木"]
    early = settle(project, task, {}, datetime(2026, 11, 3, 10))
    assert early is not None and names(early.crew) == ["田中"]
    clock_now = today
    decompose(
        project,
        (),
        0,
        [Part("x", 3.0), Part("y", 3.0), Part("z", 3.0)],
        holidays={},
        today=clock_now,
    )
    assert project.tasks[0].daily_crew == {}


def test_a_copy_has_its_own_daily_crew() -> None:
    task = daily_task()
    project = project_of(task)
    copy = copy_task(project, ((), 0), ((), 1))
    assert [names(d) for d in copy.daily_crew[0]] == [names(d) for d in DAYS]
    task.daily_crew[0][0].append(Assignee("佐藤"))
    assert names(copy.daily_crew[0][0]) == ["田中"]


def test_changing_the_kind_to_a_checkpoint_drops_the_daily_crew() -> None:
    task = daily_task()
    saved = build_task(
        task,
        name="c",
        planned_start="",
        planned_end="",
        planned_end_manual=False,
        deadline="2026-11-09T17:00",
        effort_hours=0.0,
        priority=Priority.MEDIUM,
        status=Status.NOT_STARTED,
        color="#336699",
        assignees=[],
        kind=TaskKind.CHECKPOINT,
    )
    assert saved.weekly_crew == [] and saved.daily_crew == {}


def test_saving_the_edit_form_keeps_the_daily_crew() -> None:
    task = daily_task()
    saved = build_task(
        task,
        name="a",
        planned_start="2026-11-02T09:00",
        planned_end="2026-11-12T17:00",
        planned_end_manual=False,
        deadline="",
        effort_hours=20.0,
        priority=Priority.MEDIUM,
        status=Status.NOT_STARTED,
        color="#336699",
        assignees=[],
    )
    assert [names(d) for d in saved.daily_crew[0]] == [names(d) for d in DAYS]


def test_plantuml_counts_the_daily_tasks_and_names_them_in_the_notice() -> None:
    from projectapp.plantuml import Scale, build_plantuml
    from projectapp.filtering import TaskFilter

    project = project_of(
        Task(
            "a",
            id="ta",
            planned_start=datetime(2026, 11, 2, 9),
            planned_end=datetime(2026, 11, 12, 17),
            assignees=list(TS),
            weekly_crew=[list(TS), list(T)],
            daily_crew={0: [list(d) for d in DAYS]},
        )
    )
    result = build_plantuml(
        project,
        {},
        period=(date(2026, 11, 1), date(2026, 11, 30)),
        scale=Scale.DAY,
        task_filter=TaskFilter(),
        now=datetime(2026, 11, 2, 8),
    )
    assert result.weekly_tasks == 1 and result.daily_tasks == 1
    assert "日ごとの週あり 1 件" in (weekly_crew_notice(1, 1) or "")
    assert "日ごとの週" not in (weekly_crew_notice(1) or "")


def test_handoff_estimate_follows_the_daily_crew() -> None:
    daily = daily_task(planned_start=START, effort_hours=40.0)
    weekly = daily_task(planned_start=START, effort_hours=40.0)
    weekly.daily_crew = {}
    project = project_of(daily)
    daily_hours = _estimate_hours(daily, project, "鈴木", {})
    weekly_hours = _estimate_hours(weekly, project_of(weekly), "鈴木", {})
    # 週ごと(第 1 週は 2 人)より、日ごと(水曜まで鈴木はいない)のほうが鈴木の見積もりは小さい
    assert 0 < daily_hours < weekly_hours


def test_merge_notes_when_a_weekly_edit_meets_a_daily_split() -> None:
    base_task = daily_task(daily_crew={}, weekly_crew=[list(T), list(T)])
    base_task.assignees = list(T)
    ours = daily_task(
        daily_crew={0: [list(T) for _ in range(7)]}, weekly_crew=[list(T), list(T)]
    )
    ours.assignees = list(T)
    theirs = daily_task(daily_crew={}, weekly_crew=[[Assignee("佐藤")], list(T)])
    theirs.assignees = [Assignee("佐藤"), Assignee("田中")]
    members = [
        Member("田中", id="m1"),
        Member("鈴木", id="m2"),
        Member("佐藤", id="m3"),
    ]
    result = merge_projects(
        project_of(base_task, members=members),
        project_of(ours, members=members),
        project_of(theirs, members=members),
    )
    assert any("食い違う" in n and "第1週" in n for n in result.notes)
