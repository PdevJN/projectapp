from datetime import date

import pytest

from projectapp.dateinput import SHORTCUT_LABELS, parse_date_input, parse_time_input, shortcut_dates

TODAY = date(2026, 10, 12)  # 月曜


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026-10-15", "2026-10-15"),
        ("2026/1/5", "2026-01-05"),
        ("20261015", "2026-10-15"),
        ("10/15", "2026-10-15"),
        ("1015", "2026-10-15"),
        ("  10/15 ", "2026-10-15"),
        ("10/12", "2026-10-12"),  # 今日と同じ日は、翌年にしない
    ],
)
def test_parse_date_input_reads_the_short_forms(text: str, expected: str) -> None:
    assert parse_date_input(text, TODAY, roll_forward=True) == expected


def test_a_past_day_rolls_to_next_year_only_when_asked() -> None:
    assert parse_date_input("10/01", TODAY, roll_forward=True) == "2027-10-01"
    assert parse_date_input("0101", TODAY, roll_forward=True) == "2027-01-01"
    assert parse_date_input("10/01", TODAY, roll_forward=False) == "2026-10-01"


def test_a_full_date_never_rolls() -> None:
    assert parse_date_input("2026-10-01", TODAY, roll_forward=True) == "2026-10-01"


@pytest.mark.parametrize("text", ["", "abc", "2026-1", "10/", "13/01", "1032", "2026-02-30", "10-15"])
def test_unreadable_dates_are_none(text: str) -> None:
    assert parse_date_input(text, TODAY, roll_forward=True) is None


def test_leap_day_needs_a_leap_year() -> None:
    assert parse_date_input("2/29", date(2027, 10, 1), roll_forward=False) is None  # 2027 は平年
    assert parse_date_input("2/29", date(2028, 1, 10), roll_forward=True) == "2028-02-29"
    assert parse_date_input("2/29", date(2028, 3, 1), roll_forward=True) is None  # 翌年(2029)は平年


def test_the_year_boundary_rolls_in_december() -> None:
    assert parse_date_input("1/5", date(2026, 12, 20), roll_forward=True) == "2027-01-05"


@pytest.mark.parametrize(
    "today, next_monday",
    [
        (date(2026, 10, 12), date(2026, 10, 19)),  # 月曜は +7 日
        (date(2026, 10, 14), date(2026, 10, 19)),  # 水曜
        (date(2026, 10, 18), date(2026, 10, 19)),  # 日曜は翌日
    ],
)
def test_shortcut_dates(today: date, next_monday: date) -> None:
    dates = shortcut_dates(today)
    assert list(dates) == list(SHORTCUT_LABELS)
    assert dates["today"] == today
    assert dates["tomorrow"] == date.fromordinal(today.toordinal() + 1)
    assert dates["next-monday"] == next_monday


@pytest.mark.parametrize(
    "text, expected",
    [("9", "09:00"), ("17", "17:00"), ("930", "09:30"), ("0930", "09:30"), ("1730", "17:30"), ("9:30", "09:30"), ("09:05", "09:05"), (" 9 ", "09:00")],
)
def test_parse_time_input_reads_the_short_forms(text: str, expected: str) -> None:
    assert parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "24", "24:00", "9:60", "975", "9:5", "12345", "9:3:0"])
def test_unreadable_times_are_none(text: str) -> None:
    assert parse_time_input(text) is None


def test_full_width_digits_and_symbols_are_read_like_half_width() -> None:
    assert parse_date_input("１０/１５", TODAY, roll_forward=True) == "2026-10-15"
    assert parse_date_input("１０１５", TODAY, roll_forward=True) == "2026-10-15"
    assert parse_date_input("２０２６－１０－１５", TODAY, roll_forward=True) == "2026-10-15"
    assert parse_time_input("９３０") == "09:30"
    assert parse_time_input("１０：３０") == "10:30"
    assert parse_time_input("２４：００") is None
