from datetime import date, datetime

from projectapp.bulk_edit import (
    SKIP_BEFORE_START,
    SKIP_KIND,
    SKIP_NEGATIVE,
    SKIP_NO_EFFORT,
    BulkChanges,
    CategoryChange,
    CrewChange,
    CrewMode,
    EffortChange,
    EffortMode,
    EndChange,
    EndMode,
    apply_bulk,
    delete_summary,
    delete_tasks,
    forecast_text,
    store,
)
from projectapp.models import Actual, Assignee, Member
from projectapp.models import Category, Project, Section, Task, TaskKind

START = datetime(2026, 10, 5, 9)


def project_of(*tasks: Task, section: list[Task] | None = None) -> Project:
    sections = [Section("開発", section)] if section else []
    return Project("p", base_date=date(2026, 10, 5), tasks=list(tasks), sections=sections, categories=[Category("開発", id="cat")])


def test_category_applies_to_normal_summary_and_checkpoint_but_not_reference() -> None:
    tasks = [
        Task("n", id="n"),
        Task("s", id="s", kind=TaskKind.SUMMARY, children=[]),
        Task("c", id="c", kind=TaskKind.CHECKPOINT, deadline=START),
        Task("r", id="r", kind=TaskKind.REFERENCE, ref_project="x"),
    ]
    project = project_of(*tasks)
    result = apply_bulk(project, ["n", "s", "c", "r"], BulkChanges(category=CategoryChange("cat")), {})
    assert set(result.tasks) == {"n", "s", "c"}
    assert all(t.category_id == "cat" for t in result.tasks.values())
    assert result.skips[SKIP_KIND] == 1
    assert all(t.category_id is None for t in project.all_tasks())  # ドライランは元を変えない


def test_category_none_sets_undecided() -> None:
    project = project_of(Task("n", id="n", category_id="cat"))
    result = apply_bulk(project, ["n"], BulkChanges(category=CategoryChange(None)), {})
    assert result.tasks["n"].category_id is None


def test_effort_set_converts_and_rounds_to_two_decimals() -> None:
    project = project_of(Task("n", id="n", effort_hours=3))
    result = apply_bulk(project, ["n"], BulkChanges(effort=EffortChange(EffortMode.SET, 2.456)), {})
    assert result.tasks["n"].effort_hours == 2.46


def test_effort_adjust_skips_tasks_without_effort_and_those_that_would_go_negative() -> None:
    project = project_of(
        Task("ok", id="ok", effort_hours=8), Task("none", id="none"), Task("low", id="low", effort_hours=1)
    )
    result = apply_bulk(project, ["ok", "none", "low"], BulkChanges(effort=EffortChange(EffortMode.ADJUST, -2)), {})
    assert set(result.tasks) == {"ok"} and result.tasks["ok"].effort_hours == 6
    assert result.skips[SKIP_NO_EFFORT] == 1 and result.skips[SKIP_NEGATIVE] == 1


def test_effort_skips_non_normal_tasks() -> None:
    project = project_of(Task("c", id="c", kind=TaskKind.CHECKPOINT, deadline=START))
    result = apply_bulk(project, ["c"], BulkChanges(effort=EffortChange(EffortMode.SET, 4)), {})
    assert result.tasks == {} and result.skips[SKIP_KIND] == 1


def test_end_date_uses_the_closing_time_and_switches_to_manual() -> None:
    task = Task("n", id="n", planned_start=START, effort_hours=8)  # 工数あり・自動算出
    project = project_of(task)
    result = apply_bulk(project, ["n"], BulkChanges(end=EndChange(EndMode.DATE, day=date(2026, 10, 9))), {})
    new = result.tasks["n"]
    assert new.planned_end == datetime(2026, 10, 9, 15, 30)  # 9:00 + 6.5h
    assert new.planned_end_manual is True
    assert result.manual_switched == 1


def test_end_date_before_the_start_is_skipped() -> None:
    project = project_of(Task("n", id="n", planned_start=START))
    result = apply_bulk(project, ["n"], BulkChanges(end=EndChange(EndMode.DATE, day=date(2026, 10, 1))), {})
    assert result.tasks == {} and result.skips[SKIP_BEFORE_START] == 1


def test_end_date_for_a_task_without_effort_is_not_counted_as_a_manual_switch() -> None:
    project = project_of(Task("n", id="n", planned_start=START))
    result = apply_bulk(project, ["n"], BulkChanges(end=EndChange(EndMode.DATE, day=date(2026, 10, 9))), {})
    assert result.manual_switched == 0 and result.tasks["n"].planned_end_manual is True


def test_end_shift_moves_the_current_end_by_calendar_days() -> None:
    task = Task("n", id="n", planned_start=START, planned_end=datetime(2026, 10, 7, 12))
    project = project_of(task)
    result = apply_bulk(project, ["n"], BulkChanges(end=EndChange(EndMode.SHIFT, days=3)), {})
    assert result.tasks["n"].planned_end == datetime(2026, 10, 10, 12)
    assert result.tasks["n"].planned_end_manual is True
    back = apply_bulk(project, ["n"], BulkChanges(end=EndChange(EndMode.SHIFT, days=-10)), {})
    assert back.tasks == {} and back.skips[SKIP_BEFORE_START] == 1  # 開始予定より前


def test_end_shift_skips_a_task_whose_end_cannot_be_read() -> None:
    project = project_of(Task("n", id="n"))
    result = apply_bulk(project, ["n"], BulkChanges(end=EndChange(EndMode.SHIFT, days=1)), {})
    assert result.tasks == {} and result.skipped == 1


def test_ids_are_processed_in_the_given_order_and_unknown_ids_are_ignored() -> None:
    project = project_of(Task("a", id="a"), Task("b", id="b"))
    result = apply_bulk(project, ["b", "zzz", "a"], BulkChanges(category=CategoryChange("cat")), {})
    assert list(result.tasks) == ["b", "a"]


def test_store_replaces_tasks_in_root_and_sections_keeping_order() -> None:
    project = project_of(Task("a", id="a"), section=[Task("b", id="b"), Task("c", id="c")])
    result = apply_bulk(project, ["a", "c"], BulkChanges(category=CategoryChange("cat")), {})
    store(project, result)
    assert [t.category_id for t in project.all_tasks()] == ["cat", None, "cat"]
    assert [t.id for t in project.all_tasks()] == ["a", "b", "c"]


def test_forecast_text_counts_targets_changes_and_skips_by_reason() -> None:
    project = project_of(Task("a", id="a", effort_hours=8), Task("b", id="b"))
    result = apply_bulk(project, ["a", "b"], BulkChanges(effort=EffortChange(EffortMode.ADJUST, 1)), {})
    text = forecast_text(result, 2)
    assert text.startswith("対象 2 件 / 変更 1 件")
    assert "スキップ 1 項目" in text and SKIP_NO_EFFORT in text
    assert forecast_text(apply_bulk(project, [], BulkChanges(), {}), 0) == "対象 0 件 / 変更 0 件"


def crew_project(*tasks: Task) -> Project:
    project = project_of(*tasks)
    project.members = [Member("田中", id="m1"), Member("鈴木", id="m2")]
    return project


def names(crew: list[Assignee]) -> list[tuple[str, float]]:
    return [(a.name, a.allocation) for a in crew]


def weekly(*weeks: list[Assignee]) -> list[list[Assignee]]:
    return [list(w) for w in weeks]


def test_crew_add_appends_and_updates_an_existing_member_rate() -> None:
    project = crew_project(Task("t", id="t", assignees=[Assignee("田中", 1.0)]))
    add = BulkChanges(crew=CrewChange(CrewMode.ADD, (Assignee("鈴木", 0.5),)))
    assert names(apply_bulk(project, ["t"], add, {}).tasks["t"].assignees) == [("田中", 1.0), ("鈴木", 0.5)]
    update = BulkChanges(crew=CrewChange(CrewMode.ADD, (Assignee("田中", 0.4),)))
    assert names(apply_bulk(project, ["t"], update, {}).tasks["t"].assignees) == [("田中", 0.4)]


def test_crew_add_applies_to_every_week_of_a_weekly_task_and_keeps_the_union() -> None:
    task = Task("t", id="t", assignees=[Assignee("田中", 1.0)], weekly_crew=weekly([Assignee("田中", 1.0)], [Assignee("田中", 0.5)]))
    project = crew_project(task)
    new = apply_bulk(project, ["t"], BulkChanges(crew=CrewChange(CrewMode.ADD, (Assignee("鈴木", 0.3),))), {}).tasks["t"]
    assert [names(w) for w in new.weekly_crew] == [[("田中", 1.0), ("鈴木", 0.3)], [("田中", 0.5), ("鈴木", 0.3)]]
    assert names(new.assignees) == [("田中", 1.0), ("鈴木", 0.3)]


def test_crew_remove_drops_the_member_and_notes_when_a_task_becomes_unassigned() -> None:
    project = crew_project(Task("a", id="a", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)]), Task("b", id="b", assignees=[Assignee("田中", 1.0)]))
    result = apply_bulk(project, ["a", "b"], BulkChanges(crew=CrewChange(CrewMode.REMOVE, (Assignee("田中"),))), {})
    assert names(result.tasks["a"].assignees) == [("鈴木", 1.0)]
    assert result.tasks["b"].assignees == [] and result.emptied == 1


def test_crew_remove_on_a_weekly_task_fills_emptied_weeks_from_the_neighbour() -> None:
    task = Task("t", id="t", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)], weekly_crew=weekly([Assignee("田中", 1.0), Assignee("鈴木", 1.0)], [Assignee("田中", 1.0)]))
    result = apply_bulk(crew_project(task), ["t"], BulkChanges(crew=CrewChange(CrewMode.REMOVE, (Assignee("田中"),))), {})
    new = result.tasks["t"]
    assert [names(w) for w in new.weekly_crew] == [[("鈴木", 1.0)], [("鈴木", 1.0)]]  # 第 2 週は直前の週と同じ
    assert result.filled_weeks == 1


def test_crew_remove_that_empties_every_week_ends_weekly_and_unassigns() -> None:
    task = Task("t", id="t", assignees=[Assignee("田中", 1.0)], weekly_crew=weekly([Assignee("田中", 1.0)], [Assignee("田中", 1.0)]))
    result = apply_bulk(crew_project(task), ["t"], BulkChanges(crew=CrewChange(CrewMode.REMOVE, (Assignee("田中"),))), {})
    assert result.tasks["t"].weekly_crew == [] and result.tasks["t"].assignees == [] and result.emptied == 1


def test_crew_remove_of_an_absent_member_changes_nothing() -> None:
    project = crew_project(Task("t", id="t", assignees=[Assignee("田中", 1.0)]))
    result = apply_bulk(project, ["t"], BulkChanges(crew=CrewChange(CrewMode.REMOVE, (Assignee("鈴木"),))), {})
    assert result.tasks == {} and result.skipped == 0


def test_crew_replace_swaps_the_list_and_ends_weekly_counting_it() -> None:
    plain = Task("p", id="p", assignees=[Assignee("田中", 1.0)])
    weekly_task = Task("w", id="w", assignees=[Assignee("田中", 1.0)], weekly_crew=weekly([Assignee("田中", 1.0)]))
    change = BulkChanges(crew=CrewChange(CrewMode.REPLACE, (Assignee("鈴木", 0.5),)))
    result = apply_bulk(crew_project(plain, weekly_task), ["p", "w"], change, {})
    assert names(result.tasks["p"].assignees) == [("鈴木", 0.5)]
    assert result.tasks["w"].weekly_crew == [] and names(result.tasks["w"].assignees) == [("鈴木", 0.5)]
    assert result.weeks_dropped == 1  # 週ごとが解除された件数だけ


def test_crew_skips_non_normal_tasks() -> None:
    project = crew_project(Task("s", id="s", kind=TaskKind.SUMMARY))
    result = apply_bulk(project, ["s"], BulkChanges(crew=CrewChange(CrewMode.ADD, (Assignee("田中", 1.0),))), {})
    assert result.tasks == {} and result.skips[SKIP_KIND] == 1


def test_crew_change_counts_tasks_whose_end_needs_a_review() -> None:
    # 工数あり・進捗度あり・終了でない → 換算率が変わると見直しが要る
    worked = Task("w", id="w", planned_start=START, effort_hours=20, progress=30, assignees=[Assignee("田中", 1.0)])
    fresh = Task("f", id="f", planned_start=START, effort_hours=20, assignees=[Assignee("田中", 1.0)])  # 実績も進捗度もない
    change = BulkChanges(crew=CrewChange(CrewMode.ADD, (Assignee("鈴木", 1.0),)))
    result = apply_bulk(crew_project(worked, fresh), ["w", "f"], change, {})
    assert result.review_needed == 1


def test_delete_summary_counts_summaries_children_and_running_records() -> None:
    kids = [Task("c0", id="c0"), Task("c1", id="c1", actuals=[Actual(START)])]  # c1 は実行中の区間
    summary = Task("s", id="s", kind=TaskKind.SUMMARY, children=["c0", "c1"])
    project = project_of(summary, *kids, Task("n", id="n"))
    info = delete_summary(project, ["s", "c0", "c1", "n"])
    assert (info.total, info.summaries, info.children, info.running) == (4, 1, 2, 1)


def test_delete_tasks_removes_from_sections_and_cleans_links_and_summary_children() -> None:
    kid = Task("c", id="c")
    summary = Task("s", id="s", kind=TaskKind.SUMMARY, children=["c"])
    after = Task("後続", id="after", predecessors=["c", "keep"])
    keep = Task("残る", id="keep")
    project = project_of(keep, section=[summary, kid, after])
    assert delete_tasks(project, ["s", "c"]) == 2
    assert [t.id for t in project.all_tasks()] == ["keep", "after"]
    assert project.task_map()["after"].predecessors == ["keep"]


def test_delete_tasks_leaves_children_as_normal_tasks_when_only_the_summary_goes() -> None:
    summary = Task("s", id="s", kind=TaskKind.SUMMARY, children=["c"])
    project = project_of(summary, Task("c", id="c"))
    delete_tasks(project, ["s"])
    assert [t.id for t in project.all_tasks()] == ["c"]
    assert delete_tasks(project, ["zzz"]) == 0
