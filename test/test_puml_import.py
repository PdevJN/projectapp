import os
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest

from projectapp.filtering import TaskFilter
from projectapp.models import Assignee, Project, Section, Status, Task, TaskKind
from projectapp.plantuml import build_plantuml
from projectapp.puml_import import (
    PLANTUML_OPEN_FILE_TYPES,
    PlantUmlImport,
    PlantUmlImportError,
    parse_plantuml,
    read_plantuml,
    summary,
)
from projectapp.timeline import Scale


def parse(*lines: str, name: str = "取込") -> PlantUmlImport:
    return parse_plantuml("\n".join(["@startgantt", *lines, "@endgantt"]), name)


def task_named(result: PlantUmlImport, name: str) -> Task:
    return next(t for t in result.project.all_tasks() if t.name == name)


def span(result: PlantUmlImport, name: str) -> tuple[datetime | None, datetime | None]:
    task = task_named(result, name)
    return task.planned_start, task.planned_end


def at(day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute)


END = (15, 30)  # 終業時刻(9:00 + 6.5h)


def test_a_task_with_absolute_dates_becomes_a_planned_task() -> None:
    result = parse("[設計] starts 2026-10-13 and ends 2026-10-15")
    assert span(result, "設計") == (at(13), at(15, *END))
    task = task_named(result, "設計")
    assert (task.status, task.effort_hours, task.planned_end_manual) == (Status.NOT_STARTED, 0.0, False)
    assert (result.task_count, result.skipped_lines, result.unresolved) == (1, 0, 0)


def test_title_and_project_start_name_and_date_the_project() -> None:
    result = parse("title 取込元", "Project starts 2026-10-12", "[A] starts 2026-10-13")
    assert result.project.name == "取込元" and result.project.base_date == date(2026, 10, 12)


def test_the_given_name_is_used_without_a_title() -> None:
    assert parse("[A] starts 2026-10-13", name="ファイル名").project.name == "ファイル名"


def test_keywords_are_case_insensitive_and_slashed_dates_are_read() -> None:
    result = parse("PROJECT STARTS 2026/10/12", "[A] STARTS 2026/10/13 AND ENDS 2026/10/14")
    assert result.project.base_date == date(2026, 10, 12)
    assert span(result, "A") == (at(13), at(14, *END))


def test_lasts_counts_working_days_across_a_weekend() -> None:
    assert span(parse("[A] starts 2026-10-15 and lasts 3 days"), "A")[1] == at(19, *END)


def test_lasts_skips_closed_days() -> None:
    result = parse("2026-10-16 is closed", "[A] starts 2026-10-15 and lasts 2 days")
    assert span(result, "A")[1] == at(19, *END)


def test_a_date_marked_open_overrides_the_weekend() -> None:
    result = parse("2026-10-17 is open", "[A] starts 2026-10-16 and lasts 2 days")
    assert span(result, "A")[1] == at(17, *END)


def test_a_range_can_be_closed_and_reopened_later() -> None:
    result = parse("2026-10-19 to 2026-10-20 are closed", "[A] starts 2026-10-16 and lasts 2 days")
    assert span(result, "A")[1] == at(21, *END)
    reopened = parse(
        "2026-10-19 to 2026-10-20 are closed", "2026-10-19 is open", "[A] starts 2026-10-16 and lasts 2 days"
    )
    assert span(reopened, "A")[1] == at(19, *END)


def test_a_weekday_can_be_opened() -> None:
    result = parse("saturday are open", "[A] starts 2026-10-16 and lasts 2 days")
    assert span(result, "A")[1] == at(17, *END)


def test_lasts_in_weeks_is_five_working_days_per_week() -> None:
    assert span(parse("[A] starts 2026-10-12 and lasts 1 week"), "A")[1] == at(16, *END)


def test_a_task_without_a_period_lasts_one_working_day() -> None:
    assert span(parse("[A] starts 2026-10-13"), "A") == (at(13), at(13, *END))


def test_a_start_on_a_closed_day_ends_on_the_next_working_day() -> None:
    assert span(parse("[A] starts 2026-10-17"), "A") == (at(17), at(19, *END))


def test_an_end_before_the_start_is_pulled_to_the_start() -> None:
    assert span(parse("[A] starts 2026-10-15 and ends 2026-10-13"), "A") == (at(15), at(15, *END))


def test_a_task_without_a_start_begins_on_the_project_start() -> None:
    result = parse("Project starts 2026-10-13", "[A] lasts 1 day")
    assert span(result, "A") == (at(13), at(13, *END))


def test_without_a_project_start_the_first_date_seen_is_used() -> None:
    result = parse("[A] lasts 1 day", "[B] starts 2026-10-14")
    assert span(result, "A")[0] == at(14)


TODAY = date(2026, 10, 14)  # 水曜


def parse_on_today(*lines: str) -> PlantUmlImport:
    return parse_plantuml("\n".join(["@startgantt", *lines, "@endgantt"]), "取込", TODAY)


def test_a_task_with_no_date_anywhere_starts_today() -> None:
    result = parse_on_today("[A]")
    assert span(result, "A") == (at(14), at(14, *END)) and result.unresolved == 0
    assert result.project.base_date == TODAY


def test_undated_tasks_all_start_today_and_follow_their_lasts() -> None:
    """PlantUML は、日付のないガントを 1 日目から相対の日数で描く(2021 版で確認)。"""
    result = parse_on_today("[A] lasts 2 days", "[B] lasts 3 days")
    assert span(result, "A") == (at(14), at(15, *END))
    assert span(result, "B") == (at(14), at(16, *END))


def test_a_known_date_wins_over_today() -> None:
    assert span(parse_on_today("Project starts 2026-10-20", "[A]"), "A")[0] == at(20)
    assert span(parse_on_today("[A]", "[B] starts 2026-10-15"), "A")[0] == at(15)


def test_today_is_not_used_when_the_date_cannot_be_resolved() -> None:
    """循環・参照先のない別名は、PlantUML でもエラーになる。今までどおり日程なし。"""
    result = parse_on_today("[A] starts at [Z]'s end")
    assert span(result, "A") == (None, None) and result.unresolved == 1


def test_an_invalid_date_is_not_replaced_by_today() -> None:
    for line in ("[A] starts 2026-13-40", "[A] ends 2026-13-40", "[A] happens on 2026-13-40"):
        result = parse_on_today(line)
        assert span(result, "A") == (None, None) and result.unresolved == 1, line


def test_the_default_today_is_the_current_date() -> None:
    assert span(parse("[A]"), "A")[0].date() == date.today()


def test_extreme_periods_do_not_hang() -> None:
    result = parse(
        "[A] lasts 99999 days",
        "monday are closed", "tuesday are closed", "wednesday are closed", "thursday are closed",
        "friday are closed", "saturday are closed", "sunday are closed",
        "[B] starts 2026-10-13 and lasts 2 days",
    )
    assert result.skipped_lines == 1  # lasts 99999 は読み飛ばす(A は宣言だけ残る)
    assert span(result, "A")[0] == at(13)  # 開始は最初に現れた日付
    assert span(result, "B")[0] == at(13)


def test_a_milestone_becomes_a_checkpoint_at_the_end_of_the_day() -> None:
    task = task_named(parse("[M] happens on 2026-10-23"), "M")
    assert task.kind is TaskKind.CHECKPOINT and task.deadline == at(23, *END)
    assert (task.planned_start, task.planned_end, task.status) == (None, None, Status.NOT_STARTED)


def test_sections_nest_up_to_three_levels() -> None:
    result = parse(
        "[R] starts 2026-10-13",
        "-- 開発 --", "[A] starts 2026-10-13",
        "-- 開発 / 設計 --", "[B] starts 2026-10-13",
        "-- 空 --",
        "-- P / Q / R / S --", "[C] starts 2026-10-13",
    )
    project = result.project
    assert [t.name for t in project.tasks] == ["R"]
    assert [s.name for s in project.sections] == ["開発", "空", "P"]
    dev = project.sections[0]
    assert [t.name for t in dev.tasks] == ["A"] and [s.name for s in dev.sections] == ["設計"]
    assert [t.name for t in dev.sections[0].tasks] == ["B"]
    deep = project.sections[2].sections[0].sections[0]
    assert deep.name == "R / S" and [t.name for t in deep.tasks] == ["C"]


def test_ignored_lines_are_not_counted_but_unknown_lines_are() -> None:
    result = parse(
        "' コメント", "", "printscale daily", "hide footbox",
        "2026-10-19 to 2026-10-30 are colored in lightpink",
        "[A] starts 2026-10-13", "[A] is colored in #4c8bf5",
        "saturday are closed",
    )
    assert result.skipped_lines == 0
    assert parse("[A] starts 2026-10-13", "foo bar baz").skipped_lines == 1


def test_an_invalid_date_skips_the_line_but_keeps_the_task() -> None:
    result = parse("[A] starts 2026-13-40")
    assert result.skipped_lines == 1 and result.unresolved == 1 and task_named(result, "A")


def test_task_names_are_tidied() -> None:
    result = parse("[a\tb] starts 2026-10-13", f"[{'あ' * 60}] starts 2026-10-13")
    names = [t.name for t in result.project.all_tasks()]
    assert names == ["a b", "あ" * 50]


def test_a_repeated_name_is_the_same_task() -> None:
    result = parse("[設計] as [T1] starts 2026-10-13", "[設計] as [T2] starts 2026-10-14")
    assert [t.name for t in result.project.all_tasks()] == ["設計"]  # 同じ名前は同じタスク。あとの指定が勝つ
    assert span(result, "設計")[0] == at(14)


@pytest.mark.parametrize(
    "text",
    ["", "[A] starts 2026-10-13", "@startgantt\n[A] starts 2026-10-13", "@startgantt\ntitle x\n@endgantt", "\x00\x01\x02"],
)
def test_text_without_a_diagram_or_tasks_is_refused(text: str) -> None:
    with pytest.raises(PlantUmlImportError):
        parse_plantuml(text, "x")


def test_starts_at_the_end_of_another_task_begins_on_the_next_working_day() -> None:
    result = parse("[A] starts 2026-10-15 and ends 2026-10-16", "[B] starts at [A]'s end and lasts 2 days")
    assert span(result, "B") == (at(19), at(20, *END))
    assert task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_starts_at_the_start_of_another_task_does_not_become_a_predecessor() -> None:
    result = parse("[A] starts 2026-10-15 and ends 2026-10-16", "[B] starts at [A]'s start and lasts 1 day")
    assert span(result, "B")[0] == at(15) and task_named(result, "B").predecessors == []


def test_days_after_the_end_counts_calendar_days_from_the_next_day() -> None:
    result = parse("[A] starts 2026-10-12", "[B] starts 3 days after [A]'s end")
    assert span(result, "B")[0] == at(16)  # 12 の終わりの 1 日後が 13、さらに 3 日後
    assert task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_an_arrow_makes_a_predecessor_and_starts_after_it() -> None:
    result = parse("[A] starts 2026-10-12 and ends 2026-10-13", "[B] lasts 2 days", "[A] -> [B]")
    assert span(result, "B") == (at(14), at(15, *END))
    assert task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_an_explicit_start_wins_over_an_arrow_but_the_link_is_kept() -> None:
    result = parse("[A] starts 2026-10-12", "[B] starts 2026-10-20", "[A] -> [B]")
    assert span(result, "B")[0] == at(20) and task_named(result, "B").predecessors == [task_named(result, "A").id]


def test_references_by_alias_and_forward_references_resolve() -> None:
    result = parse(
        "[B] as [T2] starts at [T1]'s end and lasts 1 day",
        "[A] as [T1] starts 2026-10-12 and ends 2026-10-12",
    )
    assert span(result, "B")[0] == at(13)


def test_chains_resolve_through_several_tasks() -> None:
    result = parse(
        "[A] starts 2026-10-12", "[B] starts at [A]'s end and lasts 1 day", "[C] starts at [B]'s end and lasts 1 day"
    )
    assert span(result, "C")[0] == at(14)


def test_a_milestone_can_follow_the_end_of_a_task() -> None:
    result = parse("[A] starts 2026-10-12 and ends 2026-10-14", "[M] happens at [A]'s end")
    task = task_named(result, "M")
    assert task.kind is TaskKind.CHECKPOINT and task.deadline == at(14, *END)
    assert task.predecessors == [task_named(result, "A").id]


def test_a_cycle_leaves_both_tasks_without_a_schedule() -> None:
    result = parse("[A] starts at [B]'s end", "[B] starts at [A]'s end")
    assert span(result, "A") == (None, None) and span(result, "B") == (None, None)
    assert result.unresolved == 2


def test_a_reference_to_an_unknown_task_is_unresolved_and_creates_nothing() -> None:
    result = parse("[A] starts at [Z]'s end")
    assert span(result, "A") == (None, None) and task_named(result, "A").predecessors == []
    assert [t.name for t in result.project.all_tasks()] == ["A"]


def test_a_task_after_an_unresolved_task_is_unresolved() -> None:
    result = parse("[A] starts at [Z]'s end", "[B] lasts 1 day", "[A] -> [B]")
    assert span(result, "B") == (None, None)


def test_assignees_create_members_and_allocations() -> None:
    result = parse(
        "[A] on {田中:50%} {鈴木} starts 2026-10-13 and ends 2026-10-13",
        "[B] on {田中} starts 2026-10-14 and ends 2026-10-14",
    )
    assert [m.name for m in result.project.members] == ["田中", "鈴木"]
    assert all(m.ratio == 1.0 for m in result.project.members) and result.created_members == 2
    assert [(a.name, a.allocation) for a in task_named(result, "A").assignees] == [("田中", 0.5), ("鈴木", 1.0)]
    assert [(a.name, a.allocation) for a in task_named(result, "B").assignees] == [("田中", 1.0)]


@pytest.mark.parametrize("percent", ["0%", "101%", "150%"])
def test_an_allocation_out_of_range_becomes_100_percent_and_is_counted(percent: str) -> None:
    result = parse(f"[A] on {{田中:{percent}}} starts 2026-10-13")
    assert task_named(result, "A").assignees[0].allocation == 1.0 and result.clamped_allocations == 1


def test_empty_and_duplicate_assignees_are_ignored() -> None:
    result = parse("[A] on {} {田中:30%} {田中:80%} starts 2026-10-13")
    assert [(a.name, a.allocation) for a in task_named(result, "A").assignees] == [("田中", 0.3)]
    assert [m.name for m in result.project.members] == ["田中"]


def test_a_checkpoint_has_no_assignees() -> None:
    result = parse("[M] on {田中} happens on 2026-10-23")
    assert task_named(result, "M").assignees == [] and result.project.members == []


@pytest.mark.parametrize(
    ("line", "status", "progress"),
    [
        ("[A] starts 2026-10-13", Status.NOT_STARTED, None),
        ("[A] starts 2026-10-13 and is 0% completed", Status.NOT_STARTED, None),
        ("[A] starts 2026-10-13 and is 1% completed", Status.RUNNING, 1),
        ("[A] starts 2026-10-13 and is 99% completed", Status.RUNNING, 99),
        ("[A] starts 2026-10-13 and is 100% completed", Status.DONE, 100),
    ],
)
def test_progress_decides_the_status_and_is_kept_as_the_task_value(
    line: str, status: Status, progress: int | None
) -> None:
    result = parse(line)
    task = task_named(result, "A")
    assert task.status is status and task.progress == progress and task.actuals == []


def test_progress_on_a_separate_line_is_kept() -> None:
    result = parse("[A] as [T1] starts 2026-10-13", "[T1] is 40% completed", "[B] starts 2026-10-13", "[C] is 0% completed")
    assert (task_named(result, "A").status, task_named(result, "A").progress) == (Status.RUNNING, 40)
    assert task_named(result, "B").progress is None and task_named(result, "C").progress is None


def test_progress_over_100_skips_the_line() -> None:
    result = parse("[A] starts 2026-10-13", "[A] is 150% completed")
    assert task_named(result, "A").status is Status.NOT_STARTED and result.skipped_lines == 1


def test_a_checkpoint_is_done_only_at_100_percent() -> None:
    assert task_named(parse("[M] happens on 2026-10-23 and is 100% completed"), "M").status is Status.DONE
    assert task_named(parse("[M] happens on 2026-10-23 and is 50% completed"), "M").status is Status.NOT_STARTED
    assert task_named(parse("[M] happens on 2026-10-23 and is 100% completed"), "M").progress is None


def test_a_milestone_without_a_date_keeps_its_progress_as_a_plain_task() -> None:
    task = task_named(parse("[M] happens at [Z]'s end and is 30% completed"), "M")
    assert task.kind is TaskKind.NORMAL and task.progress == 30


def test_a_milestone_without_a_date_is_a_plain_unscheduled_task() -> None:
    result = parse("[M] happens at [Z]'s end")
    task = task_named(result, "M")
    assert task.kind is TaskKind.NORMAL and task.deadline is None and result.unresolved == 1


def test_the_summary_lists_counts_and_notes() -> None:
    result = parse(
        "[A] on {田中:0%} starts 2026-10-13 and is 50% completed", "[B] starts at [Z]'s end", "foo bar baz"
    )
    text = summary(result)
    assert text.startswith("取り込みました(タスク 2 件、メンバー 1 人を作成)")
    for note in ("読み飛ばした行 1 行", "日程が求まらないタスク 1 件", "割り当て率を 100% にした担当 1 件"):
        assert note in text
    assert "進捗度" not in text
    assert summary(parse("[A] starts 2026-10-13")) == "取り込みました(タスク 1 件)"


def test_read_plantuml_reads_utf8_with_or_without_a_bom(tmp_path: Path) -> None:
    plain, bom = tmp_path / "a.puml", tmp_path / "b.puml"
    plain.write_text("@startgantt\n[設計] starts 2026-10-13\n@endgantt\n", encoding="utf-8")
    bom.write_text("@startgantt\n[設計] starts 2026-10-13\n@endgantt\n", encoding="utf-8-sig")
    assert read_plantuml(plain) == read_plantuml(bom)
    assert "設計" in parse_plantuml(read_plantuml(bom), "x").project.all_tasks()[0].name


def test_read_plantuml_refuses_unreadable_files(tmp_path: Path) -> None:
    binary = tmp_path / "bin.puml"
    binary.write_bytes(b"\xff\xfe\x00\x81\x82")
    with pytest.raises(PlantUmlImportError):
        read_plantuml(binary)
    with pytest.raises(PlantUmlImportError):
        read_plantuml(tmp_path / "missing.puml")


def test_the_open_file_types_are_valid_for_the_native_dialog() -> None:
    from webview.util import parse_file_type  # ネイティブのダイアログが受け付ける書式

    assert [parse_file_type(f)[1] for f in PLANTUML_OPEN_FILE_TYPES] == ["*.puml;*.plantuml;*.txt"]


def test_the_output_of_build_plantuml_comes_back() -> None:
    first = Task("設計", id="t1", planned_start=datetime(2026, 10, 13, 9), planned_end=datetime(2026, 10, 14, 15, 30),
                 assignees=[Assignee("田中", 1.0)], progress=40, status=Status.RUNNING)
    second = Task("実装", id="t2", planned_start=datetime(2026, 10, 15, 9), planned_end=datetime(2026, 10, 20, 15, 30),
                  predecessors=["t1"])
    release = Task("リリース", id="t3", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 23, 15, 30))
    project = Project("検証", tasks=[first], sections=[Section("開発", [second], [Section("運用", [release])])])
    text = build_plantuml(
        project, {}, (date(2026, 10, 12), date(2026, 10, 30)), Scale.DAY, TaskFilter(), datetime(2026, 10, 1)
    ).text
    result = parse_plantuml(text, "代わり")
    back = result.project
    assert back.name == "検証" and result.created_members == 0 and result.skipped_lines == 0
    by_name = {t.name: t for t in back.all_tasks()}
    assert set(by_name) == {"設計 (田中)", "実装", "リリース"}  # 担当者名は表示名に残る
    assert (by_name["設計 (田中)"].planned_start, by_name["設計 (田中)"].planned_end) == (at(13), at(14, *END))
    assert (by_name["実装"].planned_start, by_name["実装"].planned_end) == (at(15), at(20, *END))
    assert by_name["実装"].predecessors == [by_name["設計 (田中)"].id]
    assert by_name["リリース"].kind is TaskKind.CHECKPOINT and by_name["リリース"].deadline == at(23, *END)
    assert [t.name for t in back.tasks] == ["設計 (田中)"]
    assert [s.name for s in back.sections] == ["開発"] and [s.name for s in back.sections[0].sections] == ["運用"]
    assert by_name["設計 (田中)"].progress == 40 and by_name["設計 (田中)"].status is Status.RUNNING


PLANTUML_JAR = Path(os.environ.get("PLANTUML_JAR", "/usr/local/lib/plantuml.jar"))

SUPPORTED_SYNTAX = """@startgantt
Project starts 2026-10-12
saturday are closed
sunday are closed
2026-10-16 is closed
-- 開発 --
[設計] as [T1] starts 2026-10-13 and lasts 3 days
[T1] is 40% completed
[実装] as [T2] starts at [T1]'s end and lasts 5 days
[テスト] as [T3] starts 3 days after [T2]'s end and lasts 2 days
[準備] as [T4] starts at [T1]'s start and lasts 1 day
[T1] -> [T2]
[リリース] happens on 2026-10-30
[節目] happens at [T2]'s end
@endgantt
"""


@pytest.mark.skipif(shutil.which("java") is None or not PLANTUML_JAR.exists(), reason="java と plantuml.jar が要る")
def test_the_supported_syntax_is_accepted_by_plantuml_and_imported() -> None:
    done = subprocess.run(
        ["java", "-jar", str(PLANTUML_JAR), "-pipe", "-tsvg"], input=SUPPORTED_SYNTAX.encode(), capture_output=True, timeout=60
    )
    svg = done.stdout.decode(errors="replace")
    assert done.returncode == 0 and "<svg" in svg and "Syntax Error" not in svg
    result = parse_plantuml(SUPPORTED_SYNTAX, "検証")
    assert result.skipped_lines == 0 and result.unresolved == 0
    assert result.task_count == 6


STYLE_AND_REQUIRES = """\
@startgantt

<style>
ganttDiagram {
  task {
    BackGroundColor GreenYellow
    LineColor Green
    unstarted {
      BackGroundColor Fuchsia
      LineColor FireBrick
    }
  }
}
</style>

[Prototype design] requires 7 days
[Test prototype 0] requires 4 days
[Test prototype 50] requires 4 days
[Test prototype 100] requires 4 days

[Test prototype 0] starts at [Prototype design]'s end
[Test prototype 50] starts at [Prototype design]'s end
[Test prototype 100] starts at [Prototype design]'s end

[Test prototype 0] is 0% complete
[Test prototype 50] is 50% complete
[Test prototype 100] is 100% complete
@endgantt
"""


def test_a_style_block_requires_and_complete_are_read() -> None:
    """PlantUML の公式の書き方(`requires N days`・`is N% complete`・`<style>`)の図を、そのまま取り込める。"""
    result = parse_plantuml(STYLE_AND_REQUIRES, "x", date(2026, 10, 12))  # 月曜
    assert result.skipped_lines == 0 and result.unresolved == 0
    assert span(result, "Prototype design") == (at(12), at(20, *END))  # 稼働日 7 日(土日をはさむ)
    after = {n: span(result, n) for n in ("Test prototype 0", "Test prototype 50", "Test prototype 100")}
    assert all(start == at(21) and end == at(26, *END) for start, end in after.values())  # 7 日目の翌稼働日から 4 日
    assert task_named(result, "Test prototype 0").predecessors == [task_named(result, "Prototype design").id]
    done = task_named(result, "Test prototype 100")
    assert (done.status, done.progress) == (Status.DONE, 100)
    half = task_named(result, "Test prototype 50")
    assert (half.status, half.progress) == (Status.RUNNING, 50)
    zero = task_named(result, "Test prototype 0")
    assert (zero.status, zero.progress) == (Status.NOT_STARTED, None)


def test_requires_means_the_same_as_lasts_including_weeks() -> None:
    assert span(parse_on_today("[A] requires 2 weeks"), "A") == span(parse_on_today("[A] lasts 2 weeks"), "A")
    assert span(parse_on_today("[A] requires 1 day"), "A") == span(parse_on_today("[A] lasts 1 day"), "A")


def test_complete_and_completed_are_the_same() -> None:
    a = task_named(parse("[A] is 40% complete"), "A")
    b = task_named(parse("[A] is 40% completed"), "A")
    assert (a.status, a.progress) == (b.status, b.progress) == (Status.RUNNING, 40)


def test_style_lines_are_not_counted_as_skipped() -> None:
    assert parse("<style>", "ganttDiagram {", "task {", "}", "}", "</style>", "[A] lasts 1 day").skipped_lines == 0
    assert parse("<style>ganttDiagram { }</style>", "[A] lasts 1 day").skipped_lines == 0
    assert parse("<STYLE>", "x", "</STYLE>", "[A] lasts 1 day").skipped_lines == 0


def test_an_unclosed_style_block_still_ends_at_endgantt() -> None:
    """`</style>` がなくても、@endgantt で図は終わる(その手前のタスクは取り込める)。"""
    result = parse("[A] lasts 1 day", "<style>", "ganttDiagram {")
    assert [t.name for t in result.project.all_tasks()] == ["A"] and result.skipped_lines == 0
    with pytest.raises(PlantUmlImportError):
        parse("<style>", "[A] lasts 1 day")  # 装飾の中なので、タスクはなし
