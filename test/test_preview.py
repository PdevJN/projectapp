from datetime import date, timedelta

import pytest

from projectapp.gantt import ViewOptions
from projectapp.models import Project, Task
from projectapp.preview import (
    MAX_COLUMNS,
    PREVIEW_COMFORT_WIDTH_PX,
    PreviewSettings,
    check_column_count,
    fit_scale,
    validate_period,
)
from projectapp.timeline import Scale


def test_settings_become_read_only_view_options() -> None:
    settings = PreviewSettings(date(2026, 10, 1), date(2026, 10, 31), Scale.WEEK, show_chips=False, show_alerts=True)
    assert settings.to_options() == ViewOptions(
        period=(date(2026, 10, 1), date(2026, 10, 31)), scale=Scale.WEEK, show_chips=False, show_alerts=True, read_only=True
    )


def test_validate_period_accepts_a_period_and_one_day() -> None:
    assert validate_period("2026-10-01", "2026-10-31") == (date(2026, 10, 1), date(2026, 10, 31))
    assert validate_period(" 2026-10-05 ", "2026-10-05") == (date(2026, 10, 5), date(2026, 10, 5))


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2026-10-09", "2026-10-08", "開始日が終了日以前"),
        ("", "2026-10-08", "形式"),
        ("2026-10-01", "abc", "形式"),
        ("2026/10/01", "2026-10-08", "形式"),
        ("2026-13-01", "2026-12-31", "形式"),
        ("1999-12-31", "2026-10-08", "2000〜2100"),
        ("2026-10-01", "2101-01-01", "2000〜2100"),
    ],
)
def test_validate_period_rejects_bad_input(start: str, end: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_period(start, end)


@pytest.mark.parametrize("scale", list(Scale))
def test_check_column_count_allows_up_to_the_limit(scale: Scale) -> None:
    assert check_column_count(scale, MAX_COLUMNS[scale]) is None
    assert check_column_count(scale, 1) is None


@pytest.mark.parametrize("scale", list(Scale))
def test_check_column_count_rejects_more_than_the_limit(scale: Scale) -> None:
    message = check_column_count(scale, MAX_COLUMNS[scale] + 1)
    assert message is not None and "長すぎ" in message and str(MAX_COLUMNS[scale]) in message


def test_the_limits_allow_a_year_of_days_and_reject_the_whole_century() -> None:
    assert MAX_COLUMNS[Scale.DAY] >= 400  # 1 年強の日次は出せる
    assert MAX_COLUMNS[Scale.DAY] < 36_000  # 2000〜2100 年の全期間は、日次では出せない


BASE = date(2026, 10, 5)


def project_of_days(days: int) -> Project:
    """基準日から days 日分の列(日次)になるプロジェクト。"""
    task = Task("t", planned_start=None)
    from datetime import datetime

    task.planned_start = datetime.combine(BASE, datetime.min.time())
    task.planned_end = datetime.combine(BASE + timedelta(days=days - 1), datetime.min.time())
    task.planned_end_manual = True
    return Project("p", base_date=BASE, tasks=[task])


def width_of(project: Project, scale: Scale) -> int:
    from projectapp.gantt import COLUMN_WIDTH_PX, NAME_WIDTH_PX
    from projectapp.timeline import build_columns

    return NAME_WIDTH_PX + COLUMN_WIDTH_PX[scale] * len(build_columns(project, scale, {}))


def test_the_comfort_width_is_six_thousand_pixels() -> None:
    assert PREVIEW_COMFORT_WIDTH_PX == 6000


def test_a_narrow_project_keeps_the_scale() -> None:
    project = project_of_days(60)
    assert fit_scale(project, {}, None, Scale.DAY) is Scale.DAY
    assert fit_scale(project, {}, None, Scale.WEEK) is Scale.WEEK
    assert fit_scale(project, {}, None, Scale.MONTH) is Scale.MONTH


def test_the_boundary_is_inclusive() -> None:
    fits, too_wide = project_of_days(145), project_of_days(146)
    assert width_of(fits, Scale.DAY) == PREVIEW_COMFORT_WIDTH_PX
    assert fit_scale(fits, {}, None, Scale.DAY) is Scale.DAY
    assert width_of(too_wide, Scale.DAY) > PREVIEW_COMFORT_WIDTH_PX
    assert fit_scale(too_wide, {}, None, Scale.DAY) is Scale.WEEK


def test_a_wide_project_goes_from_day_to_week() -> None:
    project = project_of_days(421)  # 来年度のタスクがある
    assert width_of(project, Scale.DAY) > PREVIEW_COMFORT_WIDTH_PX
    assert width_of(project, Scale.WEEK) <= PREVIEW_COMFORT_WIDTH_PX
    assert fit_scale(project, {}, None, Scale.DAY) is Scale.WEEK


def test_a_very_wide_project_goes_to_month() -> None:
    project = project_of_days(800)
    assert width_of(project, Scale.WEEK) > PREVIEW_COMFORT_WIDTH_PX
    assert fit_scale(project, {}, None, Scale.DAY) is Scale.MONTH
    assert fit_scale(project, {}, None, Scale.WEEK) is Scale.MONTH


def test_month_stays_month_even_when_it_is_too_wide() -> None:
    project = project_of_days(3650)
    assert width_of(project, Scale.MONTH) > PREVIEW_COMFORT_WIDTH_PX
    assert fit_scale(project, {}, None, Scale.DAY) is Scale.MONTH


def test_it_never_goes_finer_than_the_current_scale() -> None:
    assert fit_scale(project_of_days(30), {}, None, Scale.MONTH) is Scale.MONTH


def test_the_period_decides_the_width() -> None:
    project = project_of_days(800)
    assert fit_scale(project, {}, (BASE, BASE + timedelta(days=30)), Scale.DAY) is Scale.DAY
