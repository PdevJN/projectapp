from datetime import date, datetime, time, timedelta

import pytest

from projectapp.models import Actual, Member, Project, Section, Status, Task
from projectapp.timeline import (
    actual_end,
    Band,
    Scale,
    bar_span,
    build_columns,
    Overload,
    calc_end,
    clip_overloads,
    combine_rate,
    conversion_rate,
    effort_days,
    interval_span,
    overallocations,
    deadline_position,
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


def test_deadline_position_inside_the_range() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert deadline_position(datetime(2026, 10, 7, 12), columns) == 2.5


def test_deadline_position_outside_the_range_is_none() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert deadline_position(datetime(2026, 10, 4, 23, 59), columns) is None
    assert deadline_position(datetime.combine(columns[-1].end, time.min), columns) is None


def test_deadline_position_at_the_boundaries() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    assert deadline_position(datetime(2026, 10, 5, 0, 0), columns) == 0.0
    last = datetime.combine(columns[-1].end, time.min) - timedelta(minutes=1)
    assert deadline_position(last, columns) is not None


def test_visible_range_survives_a_planned_end_at_the_end_of_time() -> None:
    task = Task("t", planned_start=datetime.max, planned_end=datetime.max)
    first, last = visible_range(project_with(task))  # 手編集のファイルでも例外にしない
    assert (first, last) == (BASE, BASE)  # 日付を足せないタスクは範囲に入れない


DEADLINE = datetime(2026, 10, 30, 18, 0)


def test_effective_end_is_the_deadline_when_the_planned_end_is_empty() -> None:
    assert eff(deadline=DEADLINE) == DEADLINE


def test_effective_end_uses_the_deadline_even_when_it_precedes_the_start() -> None:
    early = datetime(2026, 10, 1, 18, 0)
    assert eff(deadline=early) == early  # 遅れている状態が、そのまま見える


def test_effective_end_prefers_the_computed_end_over_the_deadline() -> None:
    assert eff(deadline=DEADLINE, effort_hours=15.0) == datetime(2026, 10, 13, 11)


@pytest.mark.parametrize("effort", [float("inf"), 10**9])
def test_effective_end_falls_back_to_the_deadline_when_it_cannot_compute(effort: float) -> None:
    assert eff(deadline=DEADLINE, effort_hours=effort) == DEADLINE


def test_effective_end_prefers_the_planned_end_over_the_deadline() -> None:
    assert eff(planned_end=MANUAL_END, deadline=DEADLINE) == MANUAL_END
    assert eff(planned_end=MANUAL_END, planned_end_manual=True, effort_hours=15.0, deadline=DEADLINE) == MANUAL_END


def test_effective_end_with_manual_but_empty_planned_end_computes_before_the_deadline() -> None:
    assert eff(planned_end_manual=True, effort_hours=15.0, deadline=DEADLINE) == datetime(2026, 10, 13, 11)


def test_effective_end_is_the_deadline_even_without_a_start() -> None:
    assert eff(planned_start=None, deadline=DEADLINE) == DEADLINE


def test_computed_end_takes_the_deadline_as_the_fallback() -> None:
    assert computed_end(FRI_START, 0.0, 6.5, time(9, 0), {}, DEADLINE) == DEADLINE
    assert computed_end(FRI_START, 0.0, 6.5, time(9, 0), {}, None) == datetime(2026, 10, 10, 9)
    assert computed_end(None, 0.0, 6.5, time(9, 0), {}, DEADLINE) == DEADLINE
    assert computed_end(None, 0.0, 6.5, time(9, 0), {}, None) is None


def member_project(*members: Member, tasks: list[Task] | None = None) -> Project:
    return Project("p", base_date=BASE, members=list(members), tasks=tasks or [])


def test_combine_rate_multiplies_and_guards_bad_values() -> None:
    assert combine_rate(1.2, 0.5) == pytest.approx(0.6)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        assert combine_rate(bad, 1.0) == 1.0
        assert combine_rate(1.0, bad) == 1.0


def test_conversion_rate_uses_the_member_ratio_and_the_task_allocation() -> None:
    project = member_project(Member("田中", 1.2))
    assert conversion_rate(Task("t", assignee="田中", allocation=0.5), project) == pytest.approx(0.6)
    assert conversion_rate(Task("t"), project) == 1.0  # 担当者なし
    assert conversion_rate(Task("t", assignee="不明", allocation=0.5), project) == 1.0  # メンバーにいない


def test_a_faster_member_finishes_earlier() -> None:
    project = member_project(Member("田中", 1.5))
    task = Task("t", planned_start=FRI_START, effort_hours=15.0, assignee="田中")
    # 15h / 1.5 = 10h → 金6.5h + 月3.5h
    assert effective_end(task, project, {}) == datetime(2026, 10, 12, 12, 30)


def test_a_smaller_allocation_finishes_later() -> None:
    project = member_project(Member("田中", 1.0))
    task = Task("t", planned_start=FRI_START, effort_hours=6.5, assignee="田中", allocation=0.5)
    # 6.5h / 0.5 = 13h → 金6.5h + 月6.5h
    assert effective_end(task, project, {}) == datetime(2026, 10, 12, 15, 30)


def test_a_rate_of_one_changes_nothing() -> None:
    project = member_project(Member("田中", 1.0))
    task = Task("t", planned_start=FRI_START, effort_hours=15.0, assignee="田中")
    assert effective_end(task, project, {}) == datetime(2026, 10, 13, 11)


def test_a_manual_planned_end_is_not_converted() -> None:
    project = member_project(Member("田中", 0.1))
    task = Task(
        "t",
        planned_start=FRI_START,
        effort_hours=15.0,
        assignee="田中",
        planned_end=MANUAL_END,
        planned_end_manual=True,
    )
    assert effective_end(task, project, {}) == MANUAL_END


def test_an_extreme_rate_falls_back_instead_of_raising() -> None:
    project = member_project(Member("田中", 0.1))
    task = Task(
        "t",
        planned_start=FRI_START,
        effort_hours=1000.0,
        assignee="田中",
        allocation=0.01,
        deadline=DEADLINE,
    )
    assert effective_end(task, project, {}) == DEADLINE  # 1,000,000h は算出できない
    no_deadline = Task(
        "t", planned_start=FRI_START, effort_hours=1000.0, assignee="田中", allocation=0.01
    )
    assert effective_end(no_deadline, project, {}) == datetime(2026, 10, 10, 9)


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf")])
def test_computed_end_ignores_an_unusable_rate(rate: float) -> None:
    assert computed_end(FRI_START, 15.0, 6.5, time(9, 0), {}, None, rate) == datetime(2026, 10, 13, 11)


def test_effort_days() -> None:
    assert effort_days(15.0, 1.0, 6.5) == pytest.approx(15 / 6.5)
    assert effort_days(15.0, 1.2 * 0.8, 6.5) == pytest.approx(15 / 0.96 / 6.5)
    assert effort_days(15.0, 0.0, 6.5) == pytest.approx(15 / 6.5)  # 使えない換算率は1.0
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        assert effort_days(bad, 1.0, 6.5) is None
    assert effort_days(8.0, 1.0, 0.0) is None


def alloc_task(name: str, start_day: int, end_day: int, allocation: float, **fields: object) -> Task:
    return Task(
        name,
        planned_start=datetime(2026, 10, start_day),
        planned_end=datetime(2026, 10, end_day),
        assignee="田中",
        allocation=allocation,
        **fields,  # type: ignore[arg-type]
    )


def over(*tasks: Task) -> list[Overload]:
    return overallocations(member_project(Member("田中"), tasks=list(tasks)), {})


def test_no_overload_when_the_periods_do_not_overlap() -> None:
    assert over(alloc_task("a", 5, 7, 1.0), alloc_task("b", 7, 9, 1.0)) == []  # 端が接するだけ


def test_exactly_one_hundred_percent_is_not_an_overload() -> None:
    assert over(alloc_task("a", 5, 9, 0.7), alloc_task("b", 5, 9, 0.3)) == []
    assert over(alloc_task("a", 5, 9, 0.1), alloc_task("b", 5, 9, 0.2), alloc_task("c", 5, 9, 0.7)) == []


def test_an_overload_is_reported_with_the_overlapping_period_and_total() -> None:
    result = over(alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6))
    assert result == [Overload("田中", datetime(2026, 10, 7), datetime(2026, 10, 9), pytest.approx(1.2))]


def test_three_tasks_partially_overlapping_merge_into_one_period_with_the_peak() -> None:
    result = over(alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6), alloc_task("c", 8, 10, 0.3))
    assert len(result) == 1
    assert (result[0].start, result[0].end) == (datetime(2026, 10, 7), datetime(2026, 10, 9))
    assert result[0].total == pytest.approx(1.5)  # 10/8〜10/9 が 0.6+0.6+0.3


def test_separate_overload_periods_stay_separate() -> None:
    result = over(
        alloc_task("a", 5, 8, 0.6),
        alloc_task("b", 6, 8, 0.6),
        alloc_task("c", 12, 15, 0.6),
        alloc_task("d", 13, 15, 0.6),
    )
    assert [(o.start.day, o.end.day) for o in result] == [(6, 8), (13, 15)]


def test_done_tasks_unassigned_tasks_and_tasks_without_a_start_are_not_counted() -> None:
    done = alloc_task("a", 5, 9, 0.6, status=Status.DONE)
    other = Task("b", planned_start=datetime(2026, 10, 5), planned_end=datetime(2026, 10, 9), allocation=0.6)
    no_start = Task("c", planned_end=datetime(2026, 10, 9), assignee="田中", allocation=0.6)
    assert over(done, other, no_start, alloc_task("d", 5, 9, 0.6)) == []


def test_a_task_that_ends_before_it_starts_is_not_counted() -> None:
    assert over(alloc_task("a", 9, 5, 0.6), alloc_task("b", 5, 9, 0.6)) == []


def test_tasks_of_other_members_do_not_mix() -> None:
    mine = alloc_task("a", 5, 9, 0.6)
    theirs = Task(
        "b",
        planned_start=datetime(2026, 10, 5),
        planned_end=datetime(2026, 10, 9),
        assignee="鈴木",
        allocation=0.6,
    )
    project = member_project(Member("田中"), Member("鈴木"), tasks=[mine, theirs])
    assert overallocations(project, {}) == []


def test_clip_overloads_returns_the_part_inside_the_task() -> None:
    a, b = alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6)
    project = member_project(Member("田中"), tasks=[a, b])
    overloads = overallocations(project, {})
    assert [(o.start.day, o.end.day) for o in clip_overloads(a, project, {}, overloads)] == [(7, 9)]
    assert [(o.start.day, o.end.day) for o in clip_overloads(b, project, {}, overloads)] == [(7, 9)]


def test_clip_overloads_is_empty_for_tasks_that_are_not_counted() -> None:
    a, b = alloc_task("a", 5, 9, 0.6), alloc_task("b", 7, 12, 0.6)
    done = alloc_task("c", 5, 12, 0.6, status=Status.DONE)
    project = member_project(Member("田中"), tasks=[a, b, done])
    overloads = overallocations(project, {})
    assert clip_overloads(done, project, {}, overloads) == []
    assert clip_overloads(Task("t"), project, {}, overloads) == []


def test_interval_span_matches_bar_span() -> None:
    columns = build_columns(Project("p", base_date=BASE), Scale.DAY)
    start, end = datetime(2026, 10, 5, 12), datetime(2026, 10, 7, 12)
    assert interval_span(start, end, columns) == bar_span(start, end, columns) == (0.5, 2.0)


def done_task(end: datetime | None, *, status: Status = Status.DONE, deadline: datetime | None = None) -> Task:
    return Task(
        "t",
        planned_start=datetime(2026, 10, 5, 9),
        planned_end=datetime(2026, 10, 7, 18),
        deadline=deadline,
        status=status,
        actuals=[Actual(datetime(2026, 10, 5, 9), end)],
    )


def test_actual_end_is_the_last_end_or_none() -> None:
    assert actual_end(Task("t")) is None
    assert actual_end(done_task(None)) is None
    assert actual_end(done_task(datetime(2026, 10, 6, 18))) == datetime(2026, 10, 6, 18)
    two = Task(
        "t",
        actuals=[
            Actual(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
            Actual(datetime(2026, 10, 6, 9), None),
        ],
    )
    assert actual_end(two) is None


def test_finished_late_stays_overdue_after_the_actual_end() -> None:
    task = done_task(datetime(2026, 10, 8, 10))  # 完了予定 10/7 18:00 より後に終了
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 20)) is True


def test_finished_in_time_is_not_overdue_even_if_now_is_later() -> None:
    task = done_task(datetime(2026, 10, 7, 17), status=Status.RUNNING)
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 20)) is False


def test_finished_after_the_deadline_is_overdue() -> None:
    task = done_task(datetime(2026, 10, 6, 18), deadline=datetime(2026, 10, 6, 12))
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 20)) is True


def test_done_without_an_actual_end_is_not_overdue() -> None:
    task = done_task(None)  # 終了なしの実績 + 状態は終了
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 20)) is False


def test_not_done_without_an_actual_end_uses_now() -> None:
    task = done_task(None, status=Status.RUNNING)
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 8)) is True
    assert is_overdue(task, Project("p"), {}, datetime(2026, 10, 6)) is False
