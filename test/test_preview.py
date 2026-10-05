from datetime import date

import pytest

from projectapp.gantt import ViewOptions
from projectapp.preview import PreviewSettings, validate_period
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
