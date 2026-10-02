from datetime import date, datetime

import pytest

from projectapp.models import Project, Section, Task
from projectapp.timeline import Band, Scale, bar_span, build_columns, month_bands, year_bands

BASE = date(2026, 10, 5)  # 月曜


def project_with(*tasks: Task, base: date = BASE) -> Project:
    return Project("p", base_date=base, sections=[Section("s", list(tasks))])


def test_empty_project_uses_min_columns() -> None:
    project = Project("p", base_date=BASE)
    assert len(build_columns(project, Scale.DAY)) == 42
    assert len(build_columns(project, Scale.WEEK)) == 26
    assert len(build_columns(project, Scale.MONTH)) == 12


def test_day_columns_start_at_base_and_are_contiguous() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert columns[0].start == BASE
    assert columns[0].label == "5"
    assert all(a.end == b.start for a, b in zip(columns, columns[1:]))


def test_range_extends_to_the_day_after_last_end() -> None:
    task = Task("t", start=datetime(2026, 10, 5, 9), end=datetime(2026, 12, 31, 18))
    columns = build_columns(project_with(task), Scale.DAY)
    assert len(columns) == 88
    assert columns[-1].end == date(2027, 1, 1)


def test_range_extends_before_base_date() -> None:
    task = Task("t", start=datetime(2026, 9, 20, 9), end=datetime(2026, 9, 22, 9))
    assert build_columns(project_with(task), Scale.DAY)[0].start == date(2026, 9, 20)


def test_week_columns_start_on_monday() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 7)), Scale.WEEK)
    assert columns[0].start == date(2026, 10, 5)
    assert columns[0].end == date(2026, 10, 12)
    assert columns[0].label == "5~"


def test_month_columns_cross_the_year() -> None:
    task = Task("t", start=datetime(2026, 11, 15), end=datetime(2027, 2, 10))
    columns = build_columns(project_with(task, base=date(2026, 11, 15)), Scale.MONTH)
    assert [c.label for c in columns[:4]] == ["11月", "12月", "1月", "2月"]
    assert (columns[2].start, columns[2].end) == (date(2027, 1, 1), date(2027, 2, 1))
    assert all(a.end == b.start for a, b in zip(columns, columns[1:]))


def test_bar_span_in_day_scale() -> None:
    task = Task("t", start=datetime(2026, 10, 5, 12), end=datetime(2026, 10, 7, 12))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task, columns) == (0.5, 2.0)


def test_bar_span_in_week_scale() -> None:
    task = Task("t", start=datetime(2026, 10, 5), end=datetime(2026, 10, 12))
    columns = build_columns(project_with(task), Scale.WEEK)
    assert bar_span(task, columns) == (0.0, 1.0)


def test_bar_span_in_month_scale_is_proportional() -> None:
    task = Task("t", start=datetime(2026, 1, 16), end=datetime(2026, 2, 1))
    columns = build_columns(project_with(task, base=date(2026, 1, 1)), Scale.MONTH)
    left, width = bar_span(task, columns) or (-1.0, -1.0)
    assert left == pytest.approx(15 / 31)
    assert width == pytest.approx(16 / 31)


def test_bar_span_is_none_without_start_or_end() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert bar_span(Task("a"), columns) is None
    assert bar_span(Task("b", start=datetime(2026, 10, 5)), columns) is None
    assert bar_span(Task("c", end=datetime(2026, 10, 5)), columns) is None


def test_end_before_start_gives_zero_width_without_error() -> None:
    task = Task("bad", start=datetime(2026, 10, 8), end=datetime(2026, 10, 6))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task, columns) == (3.0, 0.0)


def test_top_level_task_extends_the_range() -> None:
    task = Task("t", start=datetime(2026, 9, 20, 9), end=datetime(2026, 12, 31, 18))
    columns = build_columns(Project("p", base_date=BASE, tasks=[task]), Scale.DAY)
    assert columns[0].start == date(2026, 9, 20)
    assert columns[-1].end == date(2027, 1, 1)


def test_day_bands_merge_columns_by_year_and_month() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 27)), Scale.DAY)
    assert year_bands(columns) == [Band("2026年", 42)]
    assert month_bands(columns) == [Band("10月", 5), Band("11月", 30), Band("12月", 7)]


def test_bands_split_at_the_year_boundary() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 12, 20)), Scale.DAY)
    assert year_bands(columns) == [Band("2026年", 12), Band("2027年", 30)]
    assert month_bands(columns) == [Band("12月", 12), Band("1月", 30)]


def test_week_belongs_to_the_month_of_its_start_date() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 26)), Scale.WEEK)
    assert month_bands(columns)[:2] == [Band("10月", 1), Band("11月", 5)]


def test_month_scale_year_bands() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 11, 15)), Scale.MONTH)
    assert year_bands(columns) == [Band("2026年", 2), Band("2027年", 10)]
