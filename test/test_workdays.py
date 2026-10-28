from datetime import date, time, timedelta

import pytest

from projectapp.models import Member, WorkDay
from projectapp.workdays import expand_range, sort_work_days, validate_work_days, work_day_map


def test_work_day_defaults_to_a_rest_day_marker_of_none() -> None:
    rest = WorkDay(date(2026, 10, 12))
    assert rest.start is None and rest.end is None
    assert Member("m").work_days == []


def test_validate_accepts_windows_and_rests() -> None:
    validate_work_days([WorkDay(date(2026, 10, 17), time(13), time(16)), WorkDay(date(2026, 10, 12))])


@pytest.mark.parametrize(
    "days",
    [
        [WorkDay(date(2026, 10, 17), time(13), time(13))],  # 開始 = 終了
        [WorkDay(date(2026, 10, 17), time(16), time(13))],  # 開始 > 終了
        [WorkDay(date(2026, 10, 17), time(13), None)],  # 片方だけ
        [WorkDay(date(2026, 10, 17), None, time(16))],
        [WorkDay(date(2026, 10, 17), time(9), time(10)), WorkDay(date(2026, 10, 17))],  # 日付の重複
        [WorkDay(date(1999, 12, 31), time(9), time(10))],  # 年の範囲外
        [WorkDay(date(2101, 1, 1))],
    ],
)
def test_validate_rejects_bad_rows(days: list[WorkDay]) -> None:
    with pytest.raises(ValueError):
        validate_work_days(days)


def test_sort_and_map() -> None:
    a, b = WorkDay(date(2026, 10, 18), time(9), time(10)), WorkDay(date(2026, 10, 12))
    assert sort_work_days([a, b]) == [b, a]
    assert work_day_map([a, b]) == {date(2026, 10, 18): a, date(2026, 10, 12): b}


def test_work_day_note_defaults_to_empty() -> None:
    assert WorkDay(date(2026, 10, 12)).note == ""


def test_validate_accepts_a_note_up_to_the_limit() -> None:
    validate_work_days([WorkDay(date(2026, 10, 12), note="あ" * 30)])


@pytest.mark.parametrize("note", ["あ" * 31, "夏季\n休暇", "夏季\u200b休暇"])
def test_validate_rejects_bad_notes(note: str) -> None:
    with pytest.raises(ValueError, match="メモ"):
        validate_work_days([WorkDay(date(2026, 10, 12), note=note)])


MON, SUN = date(2026, 10, 26), date(2026, 11, 1)  # 月曜〜翌日曜


def test_expand_range_skips_weekends_by_default_choice() -> None:
    rows, registered, off = expand_range(MON, SUN, None, "夏季休暇", [], {}, True)
    assert [w.day for w in rows] == [date(2026, 10, 26 + n) for n in range(5)]
    assert all(w.start is None and w.end is None and w.note == "夏季休暇" for w in rows)
    assert (registered, off) == (0, 2)


def test_expand_range_can_include_weekends() -> None:
    rows, _, off = expand_range(MON, SUN, None, "", [], {}, False)
    assert len(rows) == 7 and off == 0


def test_expand_range_skips_holidays_when_given() -> None:
    rows, _, off = expand_range(MON, SUN, None, "", [], {date(2026, 10, 28): "祝"}, True)
    assert date(2026, 10, 28) not in [w.day for w in rows]
    assert off == 3  # 祝日 1 日と土日 2 日


def test_expand_range_without_holiday_data_skips_only_weekends() -> None:
    rows, _, off = expand_range(MON, SUN, None, "", [], {}, True)
    assert (len(rows), off) == (5, 2)


def test_expand_range_does_not_overwrite_registered_days() -> None:
    rows, registered, _ = expand_range(MON, SUN, None, "", [date(2026, 10, 27)], {}, True)
    assert date(2026, 10, 27) not in [w.day for w in rows]
    assert (len(rows), registered) == (4, 1)


def test_expand_range_with_a_window() -> None:
    rows, _, _ = expand_range(MON, MON, (time(9), time(12)), "通院", [], {}, True)
    assert rows == [WorkDay(MON, time(9), time(12), "通院")]


def test_expand_range_strips_the_note() -> None:
    (row,), _, _ = expand_range(MON, MON, None, "  通院  ", [], {}, True)
    assert row.note == "通院"


def test_expand_range_accepts_exactly_the_limit_and_rejects_one_more() -> None:
    start = date(2026, 1, 1)
    rows, _, _ = expand_range(start, start + timedelta(days=365), None, "", [], {}, False)
    assert len(rows) == 366
    with pytest.raises(ValueError, match="366"):
        expand_range(start, start + timedelta(days=366), None, "", [], {}, False)


@pytest.mark.parametrize(
    ("start", "end", "window", "note", "message"),
    [
        (SUN, MON, None, "", "開始日"),  # 開始が終了より後
        (MON, SUN, (time(12), time(9)), "", "開始"),  # 時間帯が逆
        (MON, SUN, (time(9), time(9)), "", "開始"),
        (MON, SUN, None, "あ" * 31, "メモ"),
        (date(2100, 12, 30), date(2101, 1, 2), None, "", "2100"),  # 年の範囲外
    ],
)
def test_expand_range_rejects_bad_input(start: date, end: date, window, note: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        expand_range(start, end, window, note, [], {}, False)
