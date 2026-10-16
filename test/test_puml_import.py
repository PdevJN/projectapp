from datetime import date, datetime

import pytest

from projectapp.models import Status, Task, TaskKind
from projectapp.puml_import import PlantUmlImport, PlantUmlImportError, parse_plantuml


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


def test_a_task_with_no_date_anywhere_has_no_schedule() -> None:
    result = parse("[A]")
    assert span(result, "A") == (None, None) and result.unresolved == 1


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
