from datetime import date, datetime
from pathlib import Path

from projectapp.csv_export import (
    TSV_FILE_TYPES,
    build_tsv,
    default_filename,
    format_date,
    split_name,
    write_tsv,
)
from projectapp.csv_import import parse_csv
from projectapp.models import Assignee, Member, Project, Section, Status, Task, TaskKind
from test_csv_import import SAMPLE

HEADER = "WBS 番号\tタスクのタイトル\tタスクオーナー\t開始日\t期限\t期間\tタスク完了率"


def rows(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.split("\n") if line]


def planned(name: str, start: datetime, hours: float, **kwargs) -> Task:
    return Task(name, planned_start=start, effort_hours=hours, **kwargs)


def test_dates_are_written_with_a_two_digit_year_and_no_padding() -> None:
    assert format_date(date(2026, 10, 5)) == "26年 10月 5日"
    assert format_date(date(2005, 3, 12)) == "05年 3月 12日"
    assert format_date(date(2100, 1, 1)) == "2100年 1月 1日"  # 2 桁にできない年は 4 桁


def test_a_name_is_split_at_the_first_hash_when_the_front_is_a_wbs_number() -> None:
    assert split_name("1.1#プロジェクト憲章") == ("1.1", "プロジェクト憲章")
    assert split_name("1#a#b") == ("1", "a#b")
    assert split_name("設計") == ("", "設計")
    assert split_name("A#設計") == ("", "A#設計")  # 番号でなければ分けない
    assert split_name("#設計") == ("", "#設計")


def test_the_sample_round_trips_to_the_same_rows() -> None:
    result = parse_csv(SAMPLE, "sample", {})
    out = build_tsv(result.project, {})
    assert rows(out.text) == [
        HEADER.split("\t"),
        ["1", "プロジェクトの概念化と開始", "", "", "", "", ""],
        ["1.1", "プロジェクト憲章", "オーナー名", "18年 3月 12日", "18年 3月 15日", "3", "100%"],
        ["1.1.1", "プロジェクト憲章の修正", "オーナー名", "18年 3月 15日", "18年 3月 16日", "1", "100%"],
        ["1.2", "リサーチ", "オーナー名", "18年 3月 15日", "18年 3月 21日", "6", "90%"],
        ["1.6", "プロジェクトの開始", "オーナー名", "18年 3月 23日", "18年 3月 23日", "0", "50%"],
    ]
    assert (out.task_count, out.section_count) == (4, 1)


def test_the_written_file_can_be_imported_again() -> None:
    first = parse_csv(SAMPLE, "sample", {})
    again = parse_csv(build_tsv(first.project, {}).text, "sample", {})
    assert [s.name for s in again.project.sections] == [s.name for s in first.project.sections]
    assert [(t.name, t.planned_start, t.effort_hours, t.progress, t.status) for t in again.project.all_tasks()] == [
        (t.name, t.planned_start, t.effort_hours, t.progress, t.status) for t in first.project.all_tasks()
    ]


def test_root_tasks_come_first_then_sections_depth_first() -> None:
    inner = Section("1.1#内側", [Task("1.1.1#c")])
    project = Project("p", tasks=[Task("0#root")], sections=[Section("1#外側", [Task("1.1#a")], [inner])])
    assert [r[:2] for r in rows(build_tsv(project, {}).text)[1:]] == [
        ["0", "root"],
        ["1", "外側"],
        ["1.1", "a"],
        ["1.1", "内側"],
        ["1.1.1", "c"],
    ]


def test_a_task_without_dates_or_progress_leaves_the_dates_empty_and_writes_zero_percent() -> None:
    project = Project("p", tasks=[Task("設計")])
    assert rows(build_tsv(project, {}).text)[1] == ["", "設計", "", "", "", "", "0%"]


def test_a_done_task_without_a_progress_value_is_one_hundred_percent() -> None:
    project = Project("p", tasks=[Task("a", status=Status.DONE), Task("b", progress=40)])
    assert [r[6] for r in rows(build_tsv(project, {}).text)[1:]] == ["100%", "40%"]


def test_the_end_is_the_computed_completion_day_and_the_period_counts_calendar_days() -> None:
    task = planned("a", datetime(2026, 10, 9, 9, 0), 13.0)  # 金 + 月の 2 稼働日
    row = rows(build_tsv(Project("p", tasks=[task]), {}).text)[1]
    assert row[3:6] == ["26年 10月 9日", "26年 10月 12日", "3"]


def test_the_first_assignee_is_the_owner_and_more_are_counted() -> None:
    project = Project(
        "p",
        members=[Member("田中"), Member("鈴木")],
        tasks=[Task("a", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)])],
    )
    out = build_tsv(project, {})
    assert rows(out.text)[1][2] == "田中" and out.multiple_owners == 1


def test_only_normal_tasks_are_written() -> None:
    project = Project(
        "p",
        tasks=[Task("通常"), Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9)), Task("まとめ", kind=TaskKind.SUMMARY)],
    )
    out = build_tsv(project, {})
    assert [r[1] for r in rows(out.text)[1:]] == ["通常"]
    assert (out.task_count, out.skipped) == (1, 2)


def test_a_title_with_a_tab_is_quoted() -> None:
    assert '"a\tb"' in build_tsv(Project("p", tasks=[Task("a\tb")]), {}).text


def test_the_default_filename_and_the_save_dialog_types() -> None:
    assert default_filename("案件/A") == "案件_A.tsv"
    assert default_filename("  ") == "gantt.tsv"
    assert TSV_FILE_TYPES == ("TSV ファイル (*.tsv)",)


def test_write_tsv_adds_the_extension_and_writes_utf8_without_a_bom(tmp_path: Path) -> None:
    path = write_tsv(tmp_path / "out", "あ\n")
    assert path.name == "out.tsv" and path.read_bytes() == "あ\n".encode()
