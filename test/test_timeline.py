from datetime import date, datetime, time

import pytest

from projectapp.models import Project, Section, Status, Task
from projectapp.timeline import (
    Band,
    Scale,
    bar_span,
    build_columns,
    calc_end,
    computed_end,
    effective_end,
    is_overdue,
    visible_range,
    is_workday,
    month_bands,
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
    task = Task("t", planned_start=datetime(2026, 10, 5, 9), planned_end=datetime(2026, 12, 31, 18))
    columns = build_columns(project_with(task), Scale.DAY)
    assert len(columns) == 88
    assert columns[-1].end == date(2027, 1, 1)


def test_range_extends_before_base_date() -> None:
    task = Task("t", planned_start=datetime(2026, 9, 20, 9), planned_end=datetime(2026, 9, 22, 9))
    assert build_columns(project_with(task), Scale.DAY)[0].start == date(2026, 9, 20)


def test_week_columns_start_on_monday() -> None:
    columns = build_columns(Project("p", base_date=date(2026, 10, 7)), Scale.WEEK)
    assert columns[0].start == date(2026, 10, 5)
    assert columns[0].end == date(2026, 10, 12)
    assert columns[0].label == "5~"


def test_month_columns_cross_the_year() -> None:
    task = Task("t", planned_start=datetime(2026, 11, 15), planned_end=datetime(2027, 2, 10))
    columns = build_columns(project_with(task, base=date(2026, 11, 15)), Scale.MONTH)
    assert [c.label for c in columns[:4]] == ["11月", "12月", "1月", "2月"]
    assert (columns[2].start, columns[2].end) == (date(2027, 1, 1), date(2027, 2, 1))
    assert all(a.end == b.start for a, b in zip(columns, columns[1:]))


def test_bar_span_in_day_scale() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 5, 12), planned_end=datetime(2026, 10, 7, 12))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task.planned_start, task.planned_end, columns) == (0.5, 2.0)


def test_bar_span_in_week_scale() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 12))
    columns = build_columns(project_with(task), Scale.WEEK)
    assert bar_span(task.planned_start, task.planned_end, columns) == (0.0, 1.0)


def test_bar_span_in_month_scale_is_proportional() -> None:
    task = Task("t", planned_start=datetime(2026, 1, 16), planned_end=datetime(2026, 2, 1))
    columns = build_columns(project_with(task, base=date(2026, 1, 1)), Scale.MONTH)
    left, width = bar_span(task.planned_start, task.planned_end, columns) or (-1.0, -1.0)
    assert left == pytest.approx(15 / 31)
    assert width == pytest.approx(16 / 31)


def test_bar_span_is_none_without_start_or_end() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert bar_span(None, None, columns) is None
    assert bar_span(datetime(2026, 10, 5), None, columns) is None
    assert bar_span(None, datetime(2026, 10, 5), columns) is None


def test_end_before_start_gives_zero_width_without_error() -> None:
    task = Task("bad", planned_start=datetime(2026, 10, 8), planned_end=datetime(2026, 10, 6))
    columns = build_columns(project_with(task), Scale.DAY)
    assert bar_span(task.planned_start, task.planned_end, columns) == (3.0, 0.0)


def test_top_level_task_extends_the_range() -> None:
    task = Task("t", planned_start=datetime(2026, 9, 20, 9), planned_end=datetime(2026, 12, 31, 18))
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


@pytest.mark.parametrize("effort", [float("nan"), float("inf"), float("-inf"), 1e9, 1e12])
def test_calc_end_with_absurd_effort_is_none_and_fast(effort: float) -> None:
    assert end_of(datetime(2026, 10, 5, 9), effort) is None


def test_calc_end_accepts_effort_up_to_the_limit() -> None:
    # 上限(3650稼働日分)ちょうどは算出する
    assert end_of(datetime(2026, 10, 5, 9), 6.5 * 3650) is not None


def test_calc_end_near_the_max_date_is_none_instead_of_raising() -> None:
    assert end_of(datetime(9999, 12, 20, 9), 100) is None  # 約16稼働日で9999年を超える


def test_is_overdue_when_the_deadline_has_passed() -> None:
    task = Task("t", deadline=datetime(2026, 10, 1, 18), status=Status.RUNNING)
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 2)) is True
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 1, 17)) is False


def test_is_not_overdue_by_deadline_when_done() -> None:
    task = Task("t", deadline=datetime(2026, 10, 1, 18), status=Status.DONE)
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 2)) is False


FRI_START = datetime(2026, 10, 9, 9, 0)
MANUAL_END = datetime(2026, 10, 20, 18, 0)


def eff(
    project: Project | None = None, holidays: dict[date, str] | None = None, **fields: object
) -> datetime | None:
    values: dict[str, object] = {"planned_start": FRI_START}
    values.update(fields)
    task = Task("t", **values)  # type: ignore[arg-type]
    return effective_end(task, project or Project("p"), holidays or {})


def test_effective_end_uses_planned_end_when_there_is_no_effort() -> None:
    assert eff(planned_end=MANUAL_END) == MANUAL_END


def test_effective_end_ignores_planned_end_when_effort_is_not_manual() -> None:
    assert eff(planned_end=MANUAL_END, effort_hours=15.0) == datetime(2026, 10, 13, 11)


def test_effective_end_uses_planned_end_when_manual() -> None:
    assert eff(planned_end=MANUAL_END, planned_end_manual=True, effort_hours=15.0) == MANUAL_END


def test_effective_end_computes_when_manual_but_planned_end_is_empty() -> None:
    assert eff(planned_end_manual=True, effort_hours=15.0) == datetime(2026, 10, 13, 11)


def test_effective_end_follows_the_project_settings_and_holidays() -> None:
    project = Project("p", daily_hours=8.0)
    assert eff(project, effort_hours=15.0) == datetime(2026, 10, 12, 16)
    assert eff(holidays={date(2026, 10, 12): "祝日"}, effort_hours=15.0) == datetime(
        2026, 10, 14, 11
    )
    project.work_start = time(10, 0)
    assert eff(project, effort_hours=15.0) == datetime(2026, 10, 12, 17)  # 金10-18時の8h + 月7h


def test_effective_end_is_the_next_day_without_effort_and_planned_end() -> None:
    assert eff() == datetime(2026, 10, 10, 9, 0)


@pytest.mark.parametrize("effort", [float("inf"), float("nan"), 10**9])
def test_effective_end_falls_back_to_the_next_day_when_it_cannot_compute(effort: float) -> None:
    assert eff(effort_hours=effort) == datetime(2026, 10, 10, 9, 0)


def test_effective_end_is_none_without_a_start() -> None:
    assert eff(planned_start=None) is None
    assert eff(planned_start=None, effort_hours=8.0) is None


def test_effective_end_returns_planned_end_even_without_a_start() -> None:
    assert eff(planned_start=None, planned_end=MANUAL_END) == MANUAL_END


def test_effective_end_does_not_crash_at_the_end_of_time() -> None:
    assert eff(planned_start=datetime.max) is None


def test_computed_end_ignores_planned_end_fields() -> None:
    assert computed_end(FRI_START, 15.0, 6.5, time(9, 0), {}) == datetime(2026, 10, 13, 11)
    assert computed_end(None, 15.0, 6.5, time(9, 0), {}) is None


OVERDUE_NOW = datetime(2026, 10, 10, 12)


def overdue(task: Task, project: Project | None = None, holidays: dict[date, str] | None = None) -> bool:
    return is_overdue(task, project or Project("p"), holidays or {}, OVERDUE_NOW)


def test_overdue_by_deadline() -> None:
    assert overdue(Task("t", deadline=datetime(2026, 10, 9, 18))) is True


def test_overdue_by_planned_end() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 1, 9), planned_end=datetime(2026, 10, 2))
    assert overdue(task) is True


def test_overdue_by_the_computed_end_without_a_planned_end() -> None:
    # 開始予定の1日後(10/2 9:00)を過ぎている
    assert overdue(Task("t", planned_start=datetime(2026, 10, 1, 9))) is True


def test_not_overdue_when_neither_has_passed() -> None:
    task = Task(
        "t", planned_start=datetime(2026, 10, 10, 9), deadline=datetime(2026, 10, 30), effort_hours=1.0
    )
    assert overdue(task) is False


def test_not_overdue_exactly_at_the_limit() -> None:
    assert overdue(Task("t", deadline=OVERDUE_NOW)) is False


def test_not_overdue_when_done_or_without_any_date() -> None:
    done = Task(
        "t", planned_start=datetime(2026, 10, 1, 9), deadline=datetime(2026, 10, 2), status=Status.DONE
    )
    assert overdue(done) is False
    assert overdue(Task("t")) is False


def test_visible_range_uses_the_effective_end() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 9, 9), effort_hours=15.0)  # 完了予定は 10/13 11:00
    first, last = visible_range(project_with(task))
    assert last == date(2026, 10, 14)


def test_visible_range_survives_a_planned_end_before_the_start() -> None:
    task = Task("t", planned_start=datetime(2026, 10, 9, 9), planned_end=datetime(2026, 10, 1, 9))
    first, last = visible_range(project_with(task))
    assert first == date(2026, 10, 1)
