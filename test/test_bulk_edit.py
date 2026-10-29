from datetime import date, datetime

from projectapp.bulk_edit import (
    SKIP_BEFORE_START,
    SKIP_KIND,
    SKIP_NEGATIVE,
    SKIP_NO_EFFORT,
    BulkChanges,
    CategoryChange,
    EffortChange,
    EffortMode,
    EndChange,
    EndMode,
    apply_bulk,
    forecast_text,
    store,
)
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
