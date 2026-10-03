from datetime import date, datetime, time

import pytest

from projectapp.models import Project, Section, Status, Task
from projectapp.timeline import (
    Band,
    Scale,
    bar_span,
    build_columns,
    calc_end,
    fill_end,
    is_overdue,
    is_workday,
    month_bands,
    recalc_ends,
    year_bands,
)

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


START = time(9, 0)
NO_HOLIDAYS: dict[date, str] = {}
OCT_12 = {date(2026, 10, 12): "スポーツの日"}  # 月曜


def end_of(
    start: datetime, effort: float, holidays: dict[date, str] = NO_HOLIDAYS
) -> datetime | None:
    return calc_end(start, effort, 6.5, START, holidays)


def test_is_workday() -> None:
    assert is_workday(date(2026, 10, 5), NO_HOLIDAYS)  # 月
    assert not is_workday(date(2026, 10, 10), NO_HOLIDAYS)  # 土
    assert not is_workday(date(2026, 10, 11), NO_HOLIDAYS)  # 日
    assert not is_workday(date(2026, 10, 12), OCT_12)  # 祝日


def test_calc_end_spec_example_over_a_weekend() -> None:
    # 金曜9:00・15h・6.5h/日 → 金6.5h + 月6.5h + 火2.0h
    assert end_of(datetime(2026, 10, 9, 9), 15) == datetime(2026, 10, 13, 11)


def test_calc_end_skips_holidays() -> None:
    # 月曜が祝日なら、金6.5h + 火6.5h + 水2.0h
    assert end_of(datetime(2026, 10, 9, 9), 15, OCT_12) == datetime(2026, 10, 14, 11)


def test_calc_end_exact_slot_ends_at_the_slot_end_not_next_morning() -> None:
    assert end_of(datetime(2026, 10, 5, 9), 6.5) == datetime(2026, 10, 5, 15, 30)
    assert end_of(datetime(2026, 10, 5, 9), 13) == datetime(2026, 10, 6, 15, 30)


def test_calc_end_starting_inside_the_slot() -> None:
    assert end_of(datetime(2026, 10, 5, 10), 2) == datetime(2026, 10, 5, 12)
    # 月14:00から3h: 当日1.5h + 火9:00から1.5h
    assert end_of(datetime(2026, 10, 5, 14), 3) == datetime(2026, 10, 6, 10, 30)


def test_calc_end_before_the_work_start_counts_from_the_work_start() -> None:
    assert end_of(datetime(2026, 10, 5, 7), 1) == datetime(2026, 10, 5, 10)


def test_calc_end_after_the_slot_starts_next_workday() -> None:
    assert end_of(datetime(2026, 10, 5, 16), 1) == datetime(2026, 10, 6, 10)


def test_calc_end_starting_on_a_non_workday() -> None:
    assert end_of(datetime(2026, 10, 10, 10), 1) == datetime(2026, 10, 12, 10)  # 土
    assert end_of(datetime(2026, 10, 10, 10), 1, OCT_12) == datetime(2026, 10, 13, 10)


def test_calc_end_holiday_after_a_workday_slot() -> None:
    # 金15:00から1h: 当日0.5h + 月が祝日なので火9:00から0.5h
    assert end_of(datetime(2026, 10, 9, 15), 1, OCT_12) == datetime(2026, 10, 13, 9, 30)


def test_calc_end_across_the_new_year() -> None:
    holidays = {date(2027, 1, 1): "元日"}
    # 水12/30・木12/31で13h、残り6.5hは金1/1祝・土日を飛ばして月1/4
    assert end_of(datetime(2026, 12, 30, 9), 19.5, holidays) == datetime(2027, 1, 4, 15, 30)


def test_calc_end_with_another_work_start() -> None:
    result = calc_end(datetime(2026, 10, 5, 8, 30), 6.5, 6.5, time(8, 30), NO_HOLIDAYS)
    assert result == datetime(2026, 10, 5, 15, 0)


@pytest.mark.parametrize("effort", [0, -1, 0.0])
def test_calc_end_without_positive_effort_is_none(effort: float) -> None:
    assert end_of(datetime(2026, 10, 5, 9), effort) is None


@pytest.mark.parametrize("daily", [0, -1, 24.5])
def test_calc_end_with_unusable_daily_hours_is_none(daily: float) -> None:
    assert calc_end(datetime(2026, 10, 5, 9), 8, daily, START, NO_HOLIDAYS) is None


def test_fill_end_fills_an_empty_end() -> None:
    project = Project("p")
    task = Task("t", start=datetime(2026, 10, 9, 9), effort_hours=15.0)
    filled = fill_end(task, project, NO_HOLIDAYS)
    assert filled.end == datetime(2026, 10, 13, 11)
    assert task.end is None  # 元のTaskは変えない


def test_fill_end_keeps_a_manual_end() -> None:
    manual = datetime(2026, 10, 30, 18)
    task = Task("t", start=datetime(2026, 10, 9, 9), end=manual, effort_hours=15.0)
    assert fill_end(task, Project("p"), NO_HOLIDAYS).end == manual


@pytest.mark.parametrize(
    "task",
    [Task("no start", effort_hours=8.0), Task("no effort", start=datetime(2026, 10, 9, 9))],
)
def test_fill_end_leaves_tasks_it_cannot_compute(task: Task) -> None:
    assert fill_end(task, Project("p"), NO_HOLIDAYS) is task


NOW = datetime(2026, 10, 8, 12)


def test_is_overdue() -> None:
    late = Task("t", end=datetime(2026, 10, 8, 11, 59), status=Status.RUNNING)
    assert is_overdue(late, NOW)
    assert not is_overdue(Task("t", end=NOW, status=Status.RUNNING), NOW)  # ちょうどは超過でない
    assert not is_overdue(Task("t", end=datetime(2026, 10, 9)), NOW)
    assert not is_overdue(Task("t"), NOW)  # 終了なし
    assert not is_overdue(Task("t", end=datetime(2026, 10, 1), status=Status.DONE), NOW)


@pytest.mark.parametrize("effort", [float("nan"), float("inf"), float("-inf"), 1e9, 1e12])
def test_calc_end_with_absurd_effort_is_none_and_fast(effort: float) -> None:
    assert end_of(datetime(2026, 10, 5, 9), effort) is None


def test_calc_end_accepts_effort_up_to_the_limit() -> None:
    # 上限(3650稼働日分)ちょうどは算出する
    assert end_of(datetime(2026, 10, 5, 9), 6.5 * 3650) is not None


def test_calc_end_near_the_max_date_is_none_instead_of_raising() -> None:
    assert end_of(datetime(9999, 12, 20, 9), 100) is None  # 約16稼働日で9999年を超える


def test_fill_end_leaves_a_task_with_nan_effort() -> None:
    task = Task("t", start=datetime(2026, 10, 5, 9), effort_hours=float("nan"))
    assert fill_end(task, Project("p"), NO_HOLIDAYS) is task


def test_fill_end_marks_the_end_as_automatic() -> None:
    task = Task("t", start=datetime(2026, 10, 9, 9), effort_hours=15.0)
    assert fill_end(task, Project("p"), NO_HOLIDAYS).end_auto is True


def test_fill_end_does_not_mark_a_manual_end() -> None:
    task = Task("t", start=datetime(2026, 10, 9, 9), end=datetime(2026, 10, 30, 18), effort_hours=15.0)
    assert fill_end(task, Project("p"), NO_HOLIDAYS).end_auto is False


AUTO_START = datetime(2026, 10, 9, 9)  # 金曜
AUTO_END = datetime(2026, 10, 13, 11)  # 6.5h/日・工数15hの終了(火曜)


def auto_task(name: str = "t", **overrides: object) -> Task:
    values: dict[str, object] = {
        "start": AUTO_START,
        "end": AUTO_END,
        "effort_hours": 15.0,
        "end_auto": True,
    }
    values.update(overrides)
    return Task(name, **values)  # type: ignore[arg-type]


def test_recalc_ends_follows_daily_hours() -> None:
    project = project_with(auto_task())
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS).changed == 1
    task = project.sections[0].tasks[0]
    assert task.end == datetime(2026, 10, 12, 16)  # 金8h + 月7h
    assert task.end_auto is True


def test_recalc_ends_follows_work_start() -> None:
    project = project_with(auto_task())
    project.work_start = time(10, 0)
    assert recalc_ends(project, NO_HOLIDAYS).changed == 1
    assert project.sections[0].tasks[0].end == datetime(2026, 10, 13, 12)


def test_recalc_ends_follows_holidays() -> None:
    project = project_with(auto_task())
    assert recalc_ends(project, {date(2026, 10, 12): "祝日"}).changed == 1
    assert project.sections[0].tasks[0].end == datetime(2026, 10, 14, 11)


def test_recalc_ends_returns_zero_when_nothing_changes() -> None:
    project = project_with(auto_task())
    assert recalc_ends(project, NO_HOLIDAYS).changed == 0


def test_recalc_ends_leaves_manual_ends() -> None:
    manual = auto_task(end=datetime(2026, 10, 30, 18), end_auto=False)
    project = project_with(manual)
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS).changed == 0
    assert project.sections[0].tasks[0].end == datetime(2026, 10, 30, 18)


def test_recalc_ends_keeps_the_end_of_a_task_it_cannot_compute() -> None:
    project = project_with(auto_task(effort_hours=0.0), auto_task("no start", start=None))
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS).changed == 0
    assert [t.end for t in project.sections[0].tasks] == [AUTO_END, AUTO_END]


def test_recalc_ends_covers_sections_and_top_level_tasks_and_keeps_the_lists() -> None:
    project = Project("p", sections=[Section("s", [auto_task("a")])], tasks=[auto_task("b")])
    section_tasks, top_tasks = project.sections[0].tasks, project.tasks
    project.daily_hours = 8.0
    assert recalc_ends(project, NO_HOLIDAYS).changed == 2
    assert project.sections[0].tasks is section_tasks
    assert project.tasks is top_tasks
    assert [t.end for t in section_tasks + top_tasks] == [datetime(2026, 10, 12, 16)] * 2


def test_recalc_ends_counts_the_auto_ends_it_cannot_compute() -> None:
    project = project_with(
        auto_task("zero effort", effort_hours=0.0),
        auto_task("no start", start=None),
        auto_task("ok"),
        auto_task("manual", end_auto=False, effort_hours=0.0),
    )
    project.daily_hours = 8.0
    result = recalc_ends(project, NO_HOLIDAYS)
    assert (result.changed, result.failed) == (1, 1)  # 開始なしは対象外、手入力は数えない
