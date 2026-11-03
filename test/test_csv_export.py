from datetime import date, datetime
from pathlib import Path

import pytest

from projectapp.csv_export import (
    TSV_FILE_TYPES,
    build_tsv,
    DEFAULT_FILENAME,
    format_date,
    split_name,
    write_tsv,
)
from projectapp.csv_export import (
    build_table,
    default_filename,
    encode_table,
    format_datetime,
    write_table,
)
from projectapp.csv_import import parse_csv
from projectapp.csv_profile import SMARTSHEET, CsvColumn, CsvField, CsvProfile
from projectapp.models import (
    Actual,
    Assignee,
    Category,
    Member,
    Project,
    ReferenceValue,
    Section,
    Status,
    Task,
    TaskKind,
)
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
        [""] * 7,
        [""] * 7,
        ["1", "プロジェクトの概念化と開始", "", "", "", "", ""],
        [
            "1.1",
            "プロジェクト憲章",
            "オーナー名",
            "18年 3月 12日",
            "18年 3月 15日",
            "3",
            "100%",
        ],
        [
            "1.1.1",
            "プロジェクト憲章の修正",
            "オーナー名",
            "18年 3月 15日",
            "18年 3月 16日",
            "1",
            "100%",
        ],
        ["1.2", "リサーチ", "オーナー名", "18年 3月 15日", "18年 3月 21日", "6", "90%"],
        [
            "1.6",
            "プロジェクトの開始",
            "オーナー名",
            "18年 3月 23日",
            "18年 3月 23日",
            "0",
            "50%",
        ],
    ]
    assert (out.task_count, out.section_count) == (4, 1)


def test_the_written_file_can_be_imported_again() -> None:
    first = parse_csv(SAMPLE, "sample", {})
    again = parse_csv(build_tsv(first.project, {}).text, "sample", {})
    assert [s.name for s in again.project.sections] == [
        s.name for s in first.project.sections
    ]
    assert [
        (t.name, t.planned_start, t.effort_hours, t.progress, t.status)
        for t in again.project.all_tasks()
    ] == [
        (t.name, t.planned_start, t.effort_hours, t.progress, t.status)
        for t in first.project.all_tasks()
    ]


def test_root_tasks_come_first_then_sections_depth_first() -> None:
    inner = Section("1.1#内側", [Task("1.1.1#c")])
    project = Project(
        "p",
        tasks=[Task("0#root")],
        sections=[Section("1#外側", [Task("1.1#a")], [inner])],
    )
    assert [r[:2] for r in rows(build_tsv(project, {}).text)[3:]] == [
        ["0", "root"],
        ["1", "外側"],
        ["1.1", "a"],
        ["1.1", "内側"],
        ["1.1.1", "c"],
    ]


def test_a_task_without_dates_or_progress_leaves_the_dates_empty_and_writes_zero_percent() -> (
    None
):
    project = Project("p", tasks=[Task("設計")])
    assert rows(build_tsv(project, {}).text)[3] == ["", "設計", "", "", "", "0", "0%"]


def test_a_done_task_without_a_progress_value_is_one_hundred_percent() -> None:
    project = Project(
        "p", tasks=[Task("a", status=Status.DONE), Task("b", progress=40)]
    )
    assert [r[6] for r in rows(build_tsv(project, {}).text)[3:]] == ["100%", "40%"]


def test_the_end_is_the_computed_completion_day_and_the_period_counts_calendar_days() -> (
    None
):
    task = planned("a", datetime(2026, 10, 9, 9, 0), 13.0)  # 金 + 月の 2 稼働日
    row = rows(build_tsv(Project("p", tasks=[task]), {}).text)[3]
    assert row[3:6] == ["26年 10月 9日", "26年 10月 12日", "3"]


def test_the_first_assignee_is_the_owner_and_more_are_counted() -> None:
    project = Project(
        "p",
        members=[Member("田中"), Member("鈴木")],
        tasks=[Task("a", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 0.5)])],
    )
    out = build_tsv(project, {})
    assert rows(out.text)[3][2] == "田中" and out.multiple_owners == 1


def test_only_normal_tasks_are_written() -> None:
    project = Project(
        "p",
        tasks=[
            Task("通常"),
            Task("節目", kind=TaskKind.CHECKPOINT, deadline=datetime(2026, 10, 9)),
            Task("まとめ", kind=TaskKind.SUMMARY),
        ],
    )
    out = build_tsv(project, {})
    assert [r[1] for r in rows(out.text)[3:]] == ["通常"]
    assert (out.task_count, out.skipped) == (1, 2)


def test_a_title_with_a_tab_is_quoted() -> None:
    assert '"a\tb"' in build_tsv(Project("p", tasks=[Task("a\tb")]), {}).text


def test_the_default_filename_and_the_save_dialog_types() -> None:
    assert DEFAULT_FILENAME == "out.tsv"
    assert TSV_FILE_TYPES == ("TSV ファイル (*.tsv)",)


def test_write_tsv_adds_the_extension_and_writes_utf8_without_a_bom(
    tmp_path: Path,
) -> None:
    path = write_tsv(tmp_path / "out", "あ\n")
    assert path.name == "out.tsv" and path.read_bytes() == "あ\n".encode()


def test_two_blank_rows_follow_the_header_like_the_sample() -> None:
    lines = build_tsv(Project("p", tasks=[Task("a")]), {}).text.split("\n")
    assert lines[:3] == [HEADER, "\t" * 6, "\t" * 6] and lines[3].startswith("\ta\t")


def test_a_due_date_on_a_sunday_survives_the_round_trip() -> None:
    text = "タスクのタイトル\t開始日\t期限\t期間\nT\t2026-10-12\t2026-10-18\t6"
    row = rows(build_tsv(parse_csv(text, "w", {}).project, {}).text)[3]
    assert row[3:6] == ["26年 10月 12日", "26年 10月 18日", "6"]


def reference_project() -> Project:
    return Project(
        "p", tasks=[Task("基盤", id="r", kind=TaskKind.REFERENCE, ref_project="基盤")]
    )


def test_a_reference_row_is_written_with_the_dates_and_progress_of_its_target() -> None:
    value = ReferenceValue(
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 9, 18),
        progress=40,
    )
    out = build_tsv(reference_project(), {}, {"r": value})
    assert rows(out.text)[3] == [
        "",
        "(参照) 基盤",
        "",
        "26年 10月 5日",
        "26年 10月 9日",
        "4",
        "40%",
    ]
    assert (out.task_count, out.references, out.unresolved, out.skipped) == (0, 1, 0, 0)


def test_a_finished_reference_without_progress_is_written_as_100_percent() -> None:
    value = ReferenceValue(
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 5, 18),
        finished=True,
    )
    assert rows(build_tsv(reference_project(), {}, {"r": value}).text)[3][-1] == "100%"


def test_a_reference_without_progress_is_written_as_0_percent() -> None:
    value = ReferenceValue(
        planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 10, 5, 18)
    )
    assert rows(build_tsv(reference_project(), {}, {"r": value}).text)[3][-1] == "0%"


def test_a_reference_that_cannot_be_read_is_written_with_blank_dates_and_progress() -> (
    None
):
    out = build_tsv(reference_project(), {}, {})
    assert rows(out.text)[3] == ["", "(参照) 基盤", "", "", "", "0", ""]
    assert (out.references, out.unresolved) == (1, 1)


def test_references_default_to_unresolved_when_no_values_are_given() -> None:
    assert build_tsv(reference_project(), {}).unresolved == 1


def prof(*pairs: tuple[CsvField, str], **kw: object) -> CsvProfile:
    return CsvProfile("自作", tuple(CsvColumn(f, h) for f, h in pairs), **kw)  # type: ignore[arg-type]


def test_build_tsv_equals_build_table_with_smartsheet() -> None:
    p = Project("x")
    p.tasks.append(Task("1.1#設計", assignees=[Assignee("田中", 1.0)], progress=50))
    assert build_tsv(p, {}).text == build_table(p, {}, SMARTSHEET).text


def test_date_styles() -> None:
    d = date(2026, 10, 5)
    assert format_date(d) == "26年 10月 5日"
    assert format_date(d, "ymd-dash") == "2026-10-05"
    assert format_date(d, "ymd-slash") == "2026/10/05"
    assert (
        format_datetime(datetime(2026, 10, 5, 9, 5), "ymd-dash") == "2026-10-05 09:05"
    )


def test_columns_follow_the_profile_order_headers_and_delimiter() -> None:
    p = Project("x")
    p.tasks.append(
        Task(
            "設計",
            assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)],
            effort_hours=8,
            status=Status.RUNNING,
        )
    )
    profile = prof(
        (CsvField.STATUS, "状態"),
        (CsvField.TITLE, "件名"),
        (CsvField.OWNER, "担当"),
        (CsvField.EFFORT, "工数"),
        delimiter=";",
        owner_separator="/",
    )
    lines = build_table(p, {}, profile).text.splitlines()
    assert lines == ["状態;件名;担当;工数", "実行中;設計;田中/鈴木;8"]


def test_an_empty_separator_writes_only_the_first_owner_and_counts_it() -> None:
    p = Project("x")
    p.tasks.append(
        Task("設計", assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)])
    )
    profile = prof(
        (CsvField.TITLE, "件名"), (CsvField.OWNER, "担当"), owner_separator=""
    )
    result = build_table(p, {}, profile)
    assert result.multiple_owners == 1
    assert result.text.splitlines()[1] == "設計,田中"


def test_values_with_the_delimiter_or_quotes_are_quoted() -> None:
    p = Project("x")
    p.tasks.append(Task('A,"B"'))
    text = build_table(p, {}, prof((CsvField.TITLE, "件名"))).text
    assert text.splitlines()[1] == '"A,""B"""'


def test_actuals_category_and_effort_are_written() -> None:
    p = Project("x")
    cat = Category("開発")
    p.categories.append(cat)
    p.tasks.append(
        Task(
            "A",
            effort_hours=2.5,
            category_id=cat.id,
            actuals=[
                Actual(datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 6, 17, 30))
            ],
        )
    )
    profile = prof(
        (CsvField.TITLE, "件名"),
        (CsvField.ACTUAL_START, "開始実績"),
        (CsvField.ACTUAL_END, "終了実績"),
        (CsvField.CATEGORY, "区分"),
        (CsvField.EFFORT, "工数"),
    )
    line = build_table(p, {}, profile).text.splitlines()[1]
    assert line == "A,2026-10-05 09:00,2026-10-06 17:30,開発,2.5"


def test_sections_write_only_the_title_and_wbs() -> None:
    p = Project("x")
    p.sections.append(Section("1#計画", tasks=[Task("1.1#設計")]))
    profile = prof((CsvField.WBS, "WBS"), (CsvField.TITLE, "件名"))
    lines = build_table(p, {}, profile).text.splitlines()
    assert lines[1:] == ["1,計画", "1.1,設計"]


def test_encode_table_variants() -> None:
    assert encode_table("あ", "utf-8") == "あ".encode()
    assert encode_table("あ", "utf-8-sig") == b"\xef\xbb\xbf" + "あ".encode()
    assert encode_table("あ", "cp932") == "あ".encode("cp932")


def test_encode_table_refuses_characters_shift_jis_cannot_hold() -> None:
    with pytest.raises(ValueError, match="Shift_JIS にできない文字"):
        encode_table("🙂とA", "cp932")


def test_write_table_adds_an_extension_by_delimiter(tmp_path: Path) -> None:
    assert write_table(tmp_path / "a", b"x", "\t").name == "a.tsv"
    assert write_table(tmp_path / "b", b"x", ",").name == "b.csv"
    assert default_filename("\t") == "out.tsv" and default_filename(";") == "out.csv"


def test_a_roundtrip_through_a_custom_profile_keeps_the_content() -> None:
    p = Project("x")
    p.tasks.append(
        Task(
            "設計",
            assignees=[Assignee("田中", 1.0), Assignee("鈴木", 1.0)],
            effort_hours=3,
            status=Status.RUNNING,
        )
    )
    profile = prof(
        (CsvField.TITLE, "件名"),
        (CsvField.OWNER, "担当"),
        (CsvField.EFFORT, "工数"),
        (CsvField.STATUS, "状態"),
        delimiter=",",
        owner_separator=";",
    )
    text = build_table(p, {}, profile).text
    back = parse_csv(text, "y", {}, profile=profile, delimiter=",").project.all_tasks()[
        0
    ]
    assert back.name == "設計" and back.assignee_names == ["田中", "鈴木"]
    assert back.effort_hours == 3.0 and back.status is Status.RUNNING


def test_deadline_and_ratio_are_written() -> None:
    p = Project("x")
    p.tasks.append(
        Task(
            "設計",
            assignees=[Assignee("田中", 0.5), Assignee("鈴木", 1.0)],
            deadline=datetime(2026, 10, 9, 18, 0),
        )
    )
    profile = prof(
        (CsvField.TITLE, "件名"),
        (CsvField.OWNER, "担当"),
        (CsvField.RATIO, "割合"),
        (CsvField.DEADLINE, "締切"),
        delimiter=",",
        owner_separator=";",
        date_format="ymd-dash",
    )
    lines = build_table(p, {}, profile).text.splitlines()
    assert lines == ["件名,担当,割合,締切", "設計,田中;鈴木,50%;100%,2026-10-09"]


def test_progress_is_written_with_or_without_the_percent_sign() -> None:
    p = Project("x")
    p.tasks.append(Task("設計", progress=50))
    cols = ((CsvField.TITLE, "件名"), (CsvField.PROGRESS, "進捗率"))
    with_sign = build_table(p, {}, prof(*cols, delimiter=",")).text.splitlines()
    without = build_table(
        p, {}, prof(*cols, delimiter=",", progress_percent=False)
    ).text.splitlines()
    assert with_sign[1] == "設計,50%" and without[1] == "設計,50"
