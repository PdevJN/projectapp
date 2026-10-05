from datetime import date

import pytest

from projectapp.gantt import ViewOptions
from projectapp.preview import MAX_COLUMNS, PreviewSettings, check_column_count, validate_period
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
