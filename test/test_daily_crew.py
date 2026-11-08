from datetime import date

from projectapp.daily_crew import (
    crew_spans,
    merge_week,
    rows_of,
    segments,
    set_week_days,
    split_week,
    with_added_from,
)
from projectapp.models import Assignee, Task

T = [Assignee("田中")]
TS = [Assignee("田中"), Assignee("鈴木")]


def names(crew):
    return [a.name for a in crew]


def test_spans_are_seven_days_for_a_week_and_one_day_each_for_a_daily_week() -> None:
    days = [list(T)] * 3 + [list(TS)] * 4
    spans = crew_spans([list(TS), list(T)], {0: days})
    assert [d for d, _ in spans] == [1] * 7 + [7]
    assert names(spans[3][1]) == ["田中", "鈴木"] and names(spans[7][1]) == ["田中"]


def test_spans_ignore_a_daily_week_that_is_out_of_range_or_not_seven_days() -> None:
    assert [d for d, _ in crew_spans([list(T)], {3: [list(T)] * 7})] == [7]
    assert [d for d, _ in crew_spans([list(T)], {0: [list(T)] * 6})] == [7]


def test_with_added_from_a_week_head_does_not_make_a_daily_week() -> None:
    weekly, daily = with_added_from([list(T)], {}, 0, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中", "鈴木"]] and daily == {}
    weekly, daily = with_added_from([list(T)], {}, 7, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中"], ["田中", "鈴木"]] and daily == {}


def test_with_added_from_mid_week_makes_only_that_week_daily() -> None:
    weekly, daily = with_added_from([list(T), list(T), list(T)], {}, 10, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中"], ["田中", "鈴木"], ["田中", "鈴木"]]
    assert list(daily) == [1]
    assert [names(d) for d in daily[1]] == [["田中"]] * 3 + [["田中", "鈴木"]] * 4


def test_with_added_from_pads_weeks_and_refuses_beyond_the_limit() -> None:
    weekly, daily = with_added_from([list(T)], {}, 17, ("鈴木",))
    assert len(weekly) == 3 and list(daily) == [2]
    assert with_added_from([list(T)], {}, 7 * 52, ("鈴木",)) is None
    assert with_added_from([list(T)], {}, 7 * 52 - 1, ("鈴木",)) is not None


def test_with_added_from_an_earlier_offset_is_the_first_day() -> None:
    weekly, daily = with_added_from([list(T)], {}, -5, ("鈴木",))
    assert [names(w) for w in weekly] == [["田中", "鈴木"]] and daily == {}


def test_with_added_from_does_not_duplicate_and_keeps_an_existing_daily_week() -> None:
    days = [list(T)] * 7
    weekly, daily = with_added_from([list(T)], {0: days}, 2, ("田中", "鈴木"))
    assert [names(d) for d in daily[0]] == [["田中"]] * 2 + [["田中", "鈴木"]] * 5
    weekly, daily = with_added_from([list(T), list(T)], {0: days}, 7, ("鈴木",))
    assert names(weekly[1]) == ["田中", "鈴木"] and len(daily[0]) == 7
    assert all(names(d) == ["田中"] for d in daily[0])  # 前の週は変えない


def test_with_added_from_does_not_change_its_inputs() -> None:
    weekly, daily = [list(T)], {0: [list(T)] * 7}
    with_added_from(weekly, daily, 3, ("鈴木",))
    assert names(weekly[0]) == ["田中"] and all(names(d) == ["田中"] for d in daily[0])


def test_rows_of_a_task_without_weeks_is_one_week_of_the_assignees() -> None:
    weekly, daily = rows_of(Task("a", assignees=list(T)))
    assert [names(w) for w in weekly] == [["田中"]] and daily == {}


def test_segments_mix_weeks_and_days_and_carry_the_last_crew() -> None:
    days = [list(T)] * 3 + [list(TS)] * 4
    start = date(2026, 11, 2)
    seg = segments([list(TS), list(T)], {1: days}, start, date(2026, 11, 30))
    assert [(s.week, s.day) for s in seg] == [(0, None)] + [
        (1, j) for j in range(7)
    ] + [
        (2, None),
        (3, None),
        (4, None),
    ]
    assert seg[1].first == date(2026, 11, 9) == seg[1].last
    assert seg[0].first == start and seg[0].last == date(2026, 11, 8)
    assert [s.carried for s in seg] == [False] * 8 + [True] * 3
    assert names(seg[-1].crew) == ["田中", "鈴木"]  # 最後の日ごとの週の 7 日目が続く


def test_segments_stop_at_the_last_day() -> None:
    seg = segments([list(T)], {0: [list(T)] * 7}, date(2026, 11, 2), date(2026, 11, 4))
    assert [(s.week, s.day) for s in seg] == [(0, 0), (0, 1), (0, 2)]


def test_split_merge_and_set_week_days() -> None:
    task = Task("a", assignees=list(TS), weekly_crew=[list(TS), list(T)])
    split = split_week(task, 1)
    assert split is not None and list(split.daily_crew) == [1]
    assert all(names(d) == ["田中"] for d in split.daily_crew[1])
    days = [list(T)] * 3 + [list(TS)] * 4
    edited = set_week_days(split, 1, days)
    assert edited is not None and names(edited.weekly_crew[1]) == ["田中", "鈴木"]
    back = merge_week(edited, 1)
    assert back is not None and back.daily_crew == {}
    assert names(back.weekly_crew[1]) == ["田中"]  # 1 日目の担当


def test_split_pads_a_carried_week_with_the_last_crew_and_refuses_other_cases() -> None:
    task = Task("a", assignees=list(T), weekly_crew=[list(T)])
    split = split_week(task, 2)
    assert split is not None and len(split.weekly_crew) == 3
    assert split_week(Task("a", assignees=list(T)), 0) is None  # 週ごとでない
    assert split_week(task, 52) is None
    assert merge_week(task, 0) is None  # 日ごとでない
    assert set_week_days(task, 0, [list(T)] * 7) is None
    split0 = split_week(task, 0)
    assert split0 is not None
    assert set_week_days(split0, 0, [list(T)] * 6) is None
    assert set_week_days(split0, 0, [list(T)] * 6 + [[]]) is None
