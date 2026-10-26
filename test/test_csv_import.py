from datetime import date, datetime
from pathlib import Path

import pytest

from projectapp.csv_import import CSV_OPEN_FILE_TYPES, CsvImport, CsvImportError, parse_csv, read_table, summary
from projectapp.models import Status, Task
from projectapp.timeline import effective_end

HEADER = "WBS 番号\tタスクのタイトル\tタスクオーナー\t開始日\t期限\t期間\tタスク完了率"

SAMPLE = "\n".join(
    [
        HEADER,
        "\t\t\t\t\t\t",
        "\t\t\t\t\t\t",
        "1\tプロジェクトの概念化と開始\t\t\t\t\t",
        "1.1\tプロジェクト憲章\tオーナー名\t18年 3月 12日\t18年 3月 15日\t3\t100%",
        "1.1.1\tプロジェクト憲章の修正\tオーナー名\t18年 3月 15日\t18年 3月 16日\t1\t100%",
        "1.2\tリサーチ\tオーナー名\t18年 3月 15日\t18年 3月 21日\t6\t90%",
        "1.6\tプロジェクトの開始\tオーナー名\t18年 3月 23日\t18年 3月 23日\t0\t50%",
    ]
)


def parse(*lines: str, header: str = HEADER) -> CsvImport:
    return parse_csv("\n".join([header, *lines]), "取込", {})


def task_named(result: CsvImport, name: str) -> Task:
    return next(t for t in result.project.all_tasks() if t.name == name)


def test_the_sample_becomes_a_section_with_flat_tasks_named_with_the_wbs_number() -> None:
    result = parse_csv(SAMPLE, "sample", {})
    project = result.project
    assert project.name == "sample"
    assert [s.name for s in project.sections] == ["1#プロジェクトの概念化と開始"]
    assert [t.name for t in project.sections[0].tasks] == [
        "1.1#プロジェクト憲章",
        "1.1.1#プロジェクト憲章の修正",
        "1.2#リサーチ",
        "1.6#プロジェクトの開始",
    ]
    assert (result.task_count, result.section_count, result.created_members) == (4, 1, 1)
    assert [m.name for m in project.members] == ["オーナー名"]
    assert result.skipped_rows == 0 and result.unresolved == 0


def test_the_base_date_is_the_earliest_start() -> None:
    assert parse_csv(SAMPLE, "s", {}).project.base_date == date(2018, 3, 12)


def test_dates_progress_and_owner_are_read() -> None:
    task = task_named(parse_csv(SAMPLE, "s", {}), "1.1#プロジェクト憲章")
    assert task.planned_start == datetime(2018, 3, 12, 9, 0)
    assert [(a.name, a.allocation) for a in task.assignees] == [("オーナー名", 1.0)]
    assert (task.status, task.progress) == (Status.DONE, 100)


def test_effort_is_workdays_times_daily_hours_and_the_end_matches_the_due_date() -> None:
    result = parse_csv(SAMPLE, "s", {})
    task = task_named(result, "1.1#プロジェクト憲章")  # 月〜木の 4 稼働日
    assert (task.effort_hours, task.planned_end, task.planned_end_manual) == (26.0, None, False)
    assert effective_end(task, result.project, {}) == datetime(2018, 3, 15, 15, 30)
    assert task_named(result, "1.2#リサーチ").effort_hours == 32.5  # 木〜水の 5 稼働日
    assert task_named(result, "1.6#プロジェクトの開始").effort_hours == 6.5  # 同じ日は 1 日


def test_a_due_date_on_a_day_off_is_kept_as_a_manual_end_with_the_effort() -> None:
    task = task_named(parse("a\tT\t\t2026-10-12\t2026-10-18\t\t"), "a#T")  # 月〜日。期限が日曜
    assert (task.effort_hours, task.planned_end, task.planned_end_manual) == (32.5, datetime(2026, 10, 18, 15, 30), True)


def test_a_due_date_on_a_holiday_is_kept_too() -> None:
    result = parse_csv("タスクのタイトル\t開始日\t期限\nT\t2026-10-12\t2026-10-14", "h", {date(2026, 10, 14): "祝"})
    task = task_named(result, "T")
    assert (task.effort_hours, task.planned_end_manual) == (13.0, True)


def test_holidays_are_not_counted_as_workdays() -> None:
    result = parse_csv(SAMPLE, "s", {date(2018, 3, 13): "休日"})
    assert task_named(result, "1.1#プロジェクト憲章").effort_hours == 19.5


def test_progress_decides_the_status() -> None:
    result = parse_csv(SAMPLE, "s", {})
    assert (task_named(result, "1.2#リサーチ").status, task_named(result, "1.2#リサーチ").progress) == (Status.RUNNING, 90)
    zero = parse("a\tT\t\t2026-10-13\t2026-10-14\t\t0%")
    assert (task_named(zero, "a#T").status, task_named(zero, "a#T").progress) == (Status.NOT_STARTED, None)


def test_a_comma_separated_file_is_read_too() -> None:
    text = "WBS 番号,タスクのタイトル,タスクオーナー,開始日,期限,期間,タスク完了率\n1.1,設計,田中,2026/10/13,2026/10/15,2,50"
    result = parse_csv(text, "c", {})
    task = task_named(result, "1.1#設計")
    assert task.planned_start == datetime(2026, 10, 13, 9, 0) and task.progress == 50


def test_the_owner_column_may_be_spelled_with_no() -> None:
    result = parse("1.1\t設計\t田中\t2026-10-13\t2026-10-14\t\t", header="WBS番号\tタスクのタイトル\tタスクのオーナー\t開始日\t期限\t期間\tタスク完了率")
    assert [m.name for m in result.project.members] == ["田中"]


@pytest.mark.parametrize(
    "text",
    ["2026-10-05", "2026/10/05", "2026/10/5", "26年10月5日", "26年 10月 5日", "2026年10月5日", "２６年１０月５日"],
)
def test_every_date_format_is_read(text: str) -> None:
    task = task_named(parse(f"a\tT\t\t{text}\t{text}\t\t"), "a#T")
    assert task.planned_start == datetime(2026, 10, 5, 9, 0)


def test_a_task_without_a_wbs_number_keeps_its_title_as_the_name() -> None:
    assert task_named(parse("\t設計\t\t2026-10-13\t2026-10-14\t\t"), "設計")


def test_a_weekend_only_period_has_no_effort_and_a_direct_end() -> None:
    task = task_named(parse("a\tT\t\t2026-10-10\t2026-10-11\t\t"), "a#T")  # 土日
    assert (task.effort_hours, task.planned_start, task.planned_end) == (0.0, datetime(2026, 10, 10, 9, 0), datetime(2026, 10, 11, 15, 30))


def test_only_a_due_date_sets_the_end() -> None:
    task = task_named(parse("a\tT\t\t\t2026-10-14\t\t"), "a#T")
    assert (task.planned_start, task.effort_hours, task.planned_end) == (None, 0.0, datetime(2026, 10, 14, 15, 30))


def test_only_a_start_date_sets_the_start() -> None:
    task = task_named(parse("a\tT\t\t2026-10-14\t\t\t"), "a#T")
    assert (task.planned_start, task.planned_end, task.effort_hours) == (datetime(2026, 10, 14, 9, 0), None, 0.0)


def test_an_unreadable_date_or_a_reversed_period_leaves_the_task_without_a_schedule() -> None:
    result = parse("a\tT\t\tあした\t2026-10-14\t\t", "b\tU\t\t2026-10-15\t2026-10-14\t\t")
    for name in ("a#T", "b#U"):
        task = task_named(result, name)
        assert (task.planned_start, task.planned_end, task.effort_hours) == (None, None, 0.0)
    assert result.unresolved == 2


def test_an_unreadable_progress_is_counted_and_not_set() -> None:
    result = parse("a\tT\t\t2026-10-13\t2026-10-14\t\t0.5", "b\tU\t\t2026-10-13\t2026-10-14\t\t150%")
    assert task_named(result, "a#T").progress is None and task_named(result, "b#U").progress is None
    assert result.invalid_progress == 2


def test_a_one_level_wbs_row_is_a_section_even_with_values() -> None:
    result = parse("1\t計画\t田中\t2026-10-13\t2026-10-14\t\t50%", "1.1\t設計\t\t2026-10-13\t2026-10-14\t\t")
    assert [s.name for s in result.project.sections] == ["1#計画"]
    assert [t.name for t in result.project.sections[0].tasks] == ["1.1#設計"]
    assert result.dropped_values == 1 and result.created_members == 0


def test_an_empty_row_below_a_section_is_a_subsection() -> None:
    result = parse("1\t計画", "1.1\t設計", "1.1.1\t詳細\t\t2026-10-13\t2026-10-14\t\t", "2\t開発", "2.1\t実装\t\t2026-10-13\t2026-10-14\t\t")
    first, second = result.project.sections
    assert [s.name for s in first.sections] == ["1.1#設計"]
    assert [t.name for t in first.sections[0].tasks] == ["1.1.1#詳細"]
    assert [t.name for t in second.tasks] == ["2.1#実装"]
    assert result.section_count == 3


def test_a_section_deeper_than_three_levels_is_placed_at_the_third_level() -> None:
    result = parse("1\ta", "1.1\tb", "1.1.1\tc", "1.1.1.1\td", "1.1.1.1.1\te\t\t2026-10-13\t2026-10-14\t\t")
    third = result.project.sections[0].sections[0].sections
    assert [s.name for s in third] == ["1.1.1#c", "1.1.1.1#d"]
    assert all(not s.sections for s in third)
    assert [t.name for t in third[1].tasks] == ["1.1.1.1.1#e"] and result.section_count == 4


def test_tasks_before_any_section_stay_at_the_root() -> None:
    result = parse("1.1\t設計\t\t2026-10-13\t2026-10-14\t\t")
    assert [t.name for t in result.project.tasks] == ["1.1#設計"] and result.project.sections == []


def test_a_row_without_a_title_is_skipped_and_counted() -> None:
    result = parse("1.1\t\t田中\t2026-10-13\t2026-10-14\t\t", "1.2\t設計\t\t2026-10-13\t2026-10-14\t\t")
    assert result.task_count == 1 and result.skipped_rows == 1


def test_a_long_name_is_cut_to_the_limit() -> None:
    result = parse(f"1.1\t{'あ' * 80}\t\t2026-10-13\t2026-10-14\t\t")
    assert len(result.project.tasks[0].name) == 50


def test_a_file_without_the_title_column_is_refused() -> None:
    with pytest.raises(CsvImportError):
        parse_csv("名前\t日付\nA\t2026-10-13", "x", {})


def test_a_file_without_rows_is_refused() -> None:
    with pytest.raises(CsvImportError):
        parse_csv(HEADER + "\n\t\t\t\t\t\t", "x", {})


def test_the_same_owner_makes_one_member() -> None:
    result = parse("a\tT\t田中\t\t\t\t", "b\tU\t田中\t\t\t\t")
    assert result.created_members == 1 and len(result.project.members) == 1


def test_read_table_reads_utf8_with_bom_and_falls_back_to_shift_jis(tmp_path: Path) -> None:
    bom = tmp_path / "a.csv"
    bom.write_bytes("﻿タスクのタイトル\nあ".encode())
    assert read_table(bom) == "タスクのタイトル\nあ"
    sjis = tmp_path / "b.csv"
    sjis.write_bytes("タスクのタイトル\nあ".encode("cp932"))
    assert read_table(sjis) == "タスクのタイトル\nあ"
    with pytest.raises(CsvImportError):
        read_table(tmp_path / "missing.csv")


def test_the_open_dialog_lists_csv_and_tsv() -> None:
    assert CSV_OPEN_FILE_TYPES == ("CSV TSV ファイル (*.csv;*.tsv)",)


def test_summary_lists_the_counts_and_the_notes() -> None:
    result = parse_csv(SAMPLE, "s", {})
    assert summary(result) == "取り込みました(タスク 4 件、セクション 1 件、メンバー 1 人を作成)"
    noisy = parse("1\t計画\t田中\t2026-10-13\t\t\t", "a\t\t\t\t\t\t", "1.1\tT\t\tあ\t\t\t1.5")
    text = summary(noisy)
    assert "読み飛ばした行 1 行" in text and "日程が求まらないタスク 1 件" in text
    assert "読めない完了率 1 件" in text and "セクションの行の値を取り込まなかった行 1 行" in text


def test_every_file_dialog_filter_is_accepted_by_pywebview() -> None:
    """説明文に `/` などを入れると、pywebview がダイアログを開く前に ValueError にする(実機で見つけた)。"""
    from webview.util import parse_file_type

    from projectapp.csv_export import TSV_FILE_TYPES
    from projectapp.export import PNG_FILE_TYPES
    from projectapp.handoff import JSON_FILE_TYPES
    from projectapp.icons import ICON_FILE_TYPES
    from projectapp.plantuml import PLANTUML_FILE_TYPES
    from projectapp.puml_import import PLANTUML_OPEN_FILE_TYPES

    for types in (
        CSV_OPEN_FILE_TYPES, TSV_FILE_TYPES, PNG_FILE_TYPES, JSON_FILE_TYPES, ICON_FILE_TYPES,
        PLANTUML_FILE_TYPES, PLANTUML_OPEN_FILE_TYPES,
    ):
        for file_type in types:
            parse_file_type(file_type)
