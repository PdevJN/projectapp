from datetime import date, timedelta

import pytest

from projectapp.events import (
    CSS_COLORS,
    assign_lanes,
    cell_colors,
    color_hex,
    column_span,
    count_lanes,
    EffectiveHolidays,
    effective_holidays,
    normalize_color,
    sort_events,
    validate_events,
)
from projectapp.models import Event, Project
from projectapp.timeline import Column


def day_columns(first: date, count: int) -> list[Column]:
    return [Column(first + timedelta(days=i), first + timedelta(days=i + 1), str(i)) for i in range(count)]


def week_columns(monday: date, count: int) -> list[Column]:
    return [Column(monday + timedelta(weeks=i), monday + timedelta(weeks=i + 1), f"{i}~") for i in range(count)]


def event(start: str, end: str, text: str = "e", color: str = "red", id: str = "x") -> Event:
    return Event(date.fromisoformat(start), date.fromisoformat(end), text, color, id=id)


def test_css_colors_has_named_colors() -> None:
    assert CSS_COLORS["red"] == "#ff0000" and CSS_COLORS["orange"] == "#ffa500" and CSS_COLORS["gray"] == "#808080"
    assert CSS_COLORS["rebeccapurple"] == "#663399" and CSS_COLORS["grey"] == CSS_COLORS["gray"]
    assert "transparent" not in CSS_COLORS
    assert all(len(code) == 7 and code.startswith("#") for code in CSS_COLORS.values())
    assert len(CSS_COLORS) >= 140


@pytest.mark.parametrize(("name", "expected"), [("red", "red"), (" Red ", "red"), ("LightBlue", "lightblue"), ("#fff", None), ("transparent", None), ("", None), ("あか", None)])
def test_normalize_color(name: str, expected: str | None) -> None:
    assert normalize_color(name) == expected


def test_color_hex() -> None:
    assert color_hex("red") == "#ff0000"


def test_valid_events_pass() -> None:
    validate_events([event("2026-10-01", "2026-10-01", id="a"), event("2026-10-02", "2026-10-09", "リリース", "orange", id="b")])


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (Event(date(2026, 10, 2), date(2026, 10, 1), "e", "red", id="a"), "終了日"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "", "red", id="a"), "文字列"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "   ", "red", id="a"), "文字列"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "あ" * 31, "red", id="a"), "30"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "a\nb", "red", id="a"), "制御文字"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "a​b", "red", id="a"), "制御文字"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "e", "#ff0000", id="a"), "色"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "e", "Red", id="a"), "色"),
        (Event(date(2026, 10, 1), date(2026, 10, 1), "e", "red", id=""), "id"),
    ],
)
def test_invalid_events_are_rejected(bad: Event, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_events([bad])


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="id"):
        validate_events([event("2026-10-01", "2026-10-01", id="a"), event("2026-10-02", "2026-10-02", id="a")])


def test_thirty_characters_are_allowed() -> None:
    validate_events([event("2026-10-01", "2026-10-01", "あ" * 30, id="a")])


def test_sort_events_by_start_then_end_and_keeps_order_for_ties() -> None:
    a = event("2026-10-05", "2026-10-06", id="a")
    b = event("2026-10-01", "2026-10-09", id="b")
    c = event("2026-10-01", "2026-10-03", id="c")
    d = event("2026-10-01", "2026-10-03", id="d")
    assert [e.id for e in sort_events([a, b, c, d])] == ["c", "d", "b", "a"]


def test_lanes_non_overlapping_share_one_lane_even_when_adjacent() -> None:
    events = [event("2026-10-01", "2026-10-03"), event("2026-10-04", "2026-10-06"), event("2026-10-08", "2026-10-08")]
    assert assign_lanes(events) == [0, 0, 0]
    assert count_lanes([0, 0, 0]) == 1


def test_lanes_overlapping_stack() -> None:
    events = [event("2026-10-01", "2026-10-10"), event("2026-10-03", "2026-10-04"), event("2026-10-04", "2026-10-12"), event("2026-10-11", "2026-10-13")]
    assert assign_lanes(events) == [0, 1, 2, 0]  # 4 件目は 10/10 に終わった段 0 に入る
    assert count_lanes([0, 1, 2, 0]) == 3


def test_lanes_same_day_events_stack_and_input_order_is_kept() -> None:
    events = [event("2026-10-05", "2026-10-05"), event("2026-10-05", "2026-10-05")]
    assert assign_lanes(events) == [0, 1]


def test_lanes_follow_input_order_not_sorted_order() -> None:
    later = event("2026-10-10", "2026-10-12")
    earlier = event("2026-10-01", "2026-10-03")
    assert assign_lanes([later, earlier]) == [0, 0]


def test_count_lanes_empty() -> None:
    assert count_lanes([]) == 0


def test_column_span_days_includes_both_ends() -> None:
    columns = day_columns(date(2026, 10, 1), 10)
    assert column_span(event("2026-10-03", "2026-10-05"), columns) == (2, 3)
    assert column_span(event("2026-10-04", "2026-10-04"), columns) == (3, 1)


def test_column_span_clips_to_the_columns() -> None:
    columns = day_columns(date(2026, 10, 5), 5)  # 10/5〜10/9
    assert column_span(event("2026-10-01", "2026-10-06"), columns) == (0, 2)
    assert column_span(event("2026-10-08", "2026-10-30"), columns) == (3, 2)


def test_column_span_outside_is_none() -> None:
    columns = day_columns(date(2026, 10, 5), 5)
    assert column_span(event("2026-09-01", "2026-10-04"), columns) is None
    assert column_span(event("2026-10-10", "2026-10-12"), columns) is None
    assert column_span(event("2026-10-01", "2026-10-02"), []) is None


def test_column_span_weeks_counts_every_touched_week() -> None:
    columns = week_columns(date(2026, 10, 5), 4)  # 月曜 10/5, 10/12, 10/19, 10/26
    assert column_span(event("2026-10-11", "2026-10-12"), columns) == (0, 2)  # 日曜と翌月曜
    assert column_span(event("2026-10-14", "2026-10-14"), columns) == (1, 1)  # 1 日だけでも、その週の 1 列


def test_cell_colors_later_event_wins() -> None:
    columns = day_columns(date(2026, 10, 1), 6)
    first = event("2026-10-01", "2026-10-04", color="red", id="a")
    second = event("2026-10-03", "2026-10-05", color="blue", id="b")
    assert cell_colors([first, second], columns) == ["red", "red", "blue", "blue", "blue", None]
    assert cell_colors([second, first], columns) == ["red", "red", "red", "red", "blue", None]


def test_cell_colors_no_events() -> None:
    assert cell_colors([], day_columns(date(2026, 10, 1), 3)) == [None, None, None]


def test_lanes_by_columns_stack_events_that_share_a_week_column() -> None:
    columns = week_columns(date(2026, 10, 5), 4)
    a = event("2026-10-05", "2026-10-05", id="a")
    b = event("2026-10-07", "2026-10-07", id="b")  # 日付は重ならないが、同じ週の列に入る
    assert assign_lanes([a, b]) == [0, 0]  # 列を渡さなければ、日付で割り当てる(日次)
    assert assign_lanes([a, b], columns) == [0, 1]


def test_lanes_by_columns_share_a_lane_when_columns_do_not_touch() -> None:
    columns = week_columns(date(2026, 10, 5), 4)
    a = event("2026-10-05", "2026-10-11")  # 1 列目
    b = event("2026-10-12", "2026-10-12")  # 2 列目
    assert assign_lanes([a, b], columns) == [0, 0]


def test_lanes_by_columns_ignore_events_outside_the_columns() -> None:
    columns = week_columns(date(2026, 10, 5), 2)
    outside = event("2026-12-01", "2026-12-02", id="o")
    inside = event("2026-10-05", "2026-10-05", id="i")
    assert assign_lanes([outside, inside], columns)[1] == 0  # 描かないイベントは、段を取らない


def closed(start: str, end: str, text: str = "夏季休業", **kw: object) -> Event:
    return Event(date.fromisoformat(start), date.fromisoformat(end), text, closed=True, **kw)  # type: ignore[arg-type]


def test_effective_holidays_without_closed_events_equals_the_base() -> None:
    base = {date(2026, 10, 12): "スポーツの日"}
    project = Project("p", events=[Event(date(2026, 10, 1), date(2026, 10, 3), "リリース")])
    assert effective_holidays(project, base) == base


def test_effective_holidays_adds_every_day_of_a_closed_event() -> None:
    project = Project("p", events=[closed("2026-10-26", "2026-10-28")])
    result = effective_holidays(project, {})
    assert result == {date(2026, 10, 26 + n): "夏季休業" for n in range(3)}


def test_effective_holidays_keeps_the_holiday_name_when_they_overlap() -> None:
    base = {date(2026, 10, 27): "祝日"}
    result = effective_holidays(Project("p", events=[closed("2026-10-26", "2026-10-28")]), base)
    assert result[date(2026, 10, 27)] == "祝日" and result[date(2026, 10, 26)] == "夏季休業"


def test_effective_holidays_uses_the_earlier_event_when_closed_events_overlap() -> None:
    events = [closed("2026-10-27", "2026-10-28", "後"), closed("2026-10-26", "2026-10-27", "先")]
    result = effective_holidays(Project("p", events=events), {})
    assert result[date(2026, 10, 27)] == "先" and result[date(2026, 10, 28)] == "後"


def test_effective_holidays_does_not_change_the_base() -> None:
    base: dict[date, str] = {}
    effective_holidays(Project("p", events=[closed("2026-10-26", "2026-10-26")]), base)
    assert base == {}


def test_effective_holidays_clamps_extreme_periods_to_the_supported_years() -> None:
    project = Project("p", events=[closed("0001-01-01", "9999-12-31")])
    result = effective_holidays(project, {})
    assert min(result) == date(2000, 1, 1) and max(result) == date(2100, 12, 31)


def test_effective_holidays_cache_follows_the_events_and_the_base() -> None:
    cache = EffectiveHolidays()
    base: dict[date, str] = {}
    project = Project("p", events=[closed("2026-10-26", "2026-10-26")])
    first = cache.get(project, base)
    assert cache.get(project, base) is first  # 同じ間は使い回す
    project.events[0].end = date(2026, 10, 27)
    assert date(2026, 10, 27) in cache.get(project, base)  # イベントの変更に追従する
    project.events[0].closed = False
    assert cache.get(project, base) == {}
    assert cache.get(project, {date(2026, 10, 12): "祝"}) == {date(2026, 10, 12): "祝"}  # 祝日の差し替えに追従する
