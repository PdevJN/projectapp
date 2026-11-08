from datetime import date, datetime, time

from projectapp.models import Assignee, Task, WorkDay
from projectapp.timeline import (
    CrewTrack,
    Worker,
    calc_end,
    consumed_slices,
    crew_on,
    crew_pieces,
    crew_track,
    week_index,
    work_capacity,
)
from projectapp.workdays import work_day_map

START = datetime(2026, 11, 2, 9)  # 月曜
NONE: dict[date, str] = {}
A = Worker(1.0, {}, "田中")
B = Worker(1.0, {}, "鈴木")


def end_of(effort, weeks, holidays=NONE, start=START, weeks_start=None):
    return calc_end(
        start, effort, 6.5, time(9, 0), holidays, weeks=weeks, weeks_start=weeks_start
    )


def test_a_plain_list_of_weeks_still_works_as_seven_day_steps() -> None:
    weeks = [[A], [A, B]]
    assert end_of(60.0, weeks) == end_of(60.0, CrewTrack(weeks, 7))


def test_seven_identical_days_equal_the_week() -> None:
    week = CrewTrack([[A]], 7)
    daily = CrewTrack([[A]] * 7, 1)
    for effort in (10.0, 40.0, 60.0, 130.0):
        assert end_of(effort, week) == end_of(effort, daily)
    for stop in (datetime(2026, 11, 20, 12), datetime(2026, 12, 25, 12)):
        assert work_capacity(START, stop, 6.5, time(9, 0), NONE, weeks=week) == (
            work_capacity(START, stop, 6.5, time(9, 0), NONE, weeks=daily)
        )


def test_a_person_joining_mid_week_speeds_up_from_that_day() -> None:
    alone = end_of(26.0, CrewTrack([[A]] * 7, 1))  # 4 日(月〜木)
    joined = end_of(26.0, CrewTrack([[A]] * 2 + [[A, B]] * 5, 1))  # 水から 2 人
    assert joined < alone
    # 月・火は 1 人(13h)。水から 2 人で残り 13h は 1 日(6.5h × 2)
    assert joined == datetime(2026, 11, 4, 15, 30)


def test_the_last_daily_week_carries_its_seventh_day_on() -> None:
    track = CrewTrack([[A]] * 6 + [[A, B]], 1)  # 7 日目から 2 人、以降も 2 人
    assert end_of(130.0, track) == end_of(
        130.0, CrewTrack([[A]] * 6 + [[A, B]] * 40, 1)
    )


def test_crew_on_and_crew_pieces_follow_the_days() -> None:
    days = [[Assignee("田中")]] * 3 + [[Assignee("田中"), Assignee("鈴木")]] * 4
    task = Task(
        "a",
        assignees=[Assignee("田中"), Assignee("鈴木")],
        weekly_crew=[[Assignee("田中"), Assignee("鈴木")], [Assignee("田中")]],
        daily_crew={0: days},
    )
    start = date(2026, 11, 2)
    assert [a.name for a in crew_on(task, start, date(2026, 11, 4))] == ["田中"]
    assert [a.name for a in crew_on(task, start, date(2026, 11, 5))] == ["田中", "鈴木"]
    assert [a.name for a in crew_on(task, start, date(2026, 11, 9))] == ["田中"]
    assert [a.name for a in crew_on(task, start, date(2026, 12, 31))] == ["田中"]
    pieces = crew_pieces(task, START, datetime(2026, 11, 14, 17))
    assert len(pieces) == 8  # 日ごとの 7 日 + 次の週
    assert pieces[0][0] == START and pieces[-1][1] == datetime(2026, 11, 14, 17)
    assert pieces[3][0] == datetime(2026, 11, 5, 0)


def test_without_daily_crew_pieces_and_crew_on_are_unchanged() -> None:
    task = Task(
        "a",
        assignees=[Assignee("田中")],
        weekly_crew=[[Assignee("田中")], [Assignee("鈴木")]],
    )
    pieces = crew_pieces(task, START, datetime(2026, 11, 20, 17))
    assert [(p[0], p[1]) for p in pieces] == [
        (START, datetime(2026, 11, 9)),
        (datetime(2026, 11, 9), datetime(2026, 11, 20, 17)),
    ]


# --- 休みの扱い -----------------------------------------------------------

YEAR_END = {date(2026, 12, d): "年末年始" for d in (28, 29, 30, 31)} | {
    date(2027, 1, d): "年末年始" for d in (1, 2, 3)
}


def joining(day: date, start=datetime(2026, 12, 7, 9)) -> CrewTrack:
    """start から数えた日で、day から B が加わる担当の並び(日ごと 1 日刻み)。"""
    offset = (day - start.date()).days
    return CrewTrack([[A]] * offset + [[A, B]] * 400, 1)


def test_joining_inside_the_year_end_break_equals_joining_after_it() -> None:
    # 12/26(土)・12/27(日)・12/28〜1/3 のイベントは誰も稼働しない。効き始めは 1/4(月)
    start = datetime(2026, 12, 7, 9)
    reference = end_of(200.0, joining(date(2027, 1, 4)), YEAR_END, start)
    for day in (
        date(2026, 12, 26),
        date(2026, 12, 27),
        date(2026, 12, 28),
        date(2027, 1, 3),
    ):
        assert end_of(200.0, joining(day), YEAR_END, start) == reference
    assert end_of(200.0, joining(date(2026, 12, 25)), YEAR_END, start) < reference


def test_a_daily_week_that_spans_the_new_year_counts_each_calendar_day() -> None:
    # 週の起点 12/30(水)。7 日 = 12/30〜1/5。1/4・1/5 だけ 2 人
    start = datetime(2026, 12, 30, 9)
    crews = [[A]] * 5 + [[A, B]] * 2
    capacity = work_capacity(
        start,
        datetime(2027, 1, 6),
        6.5,
        time(9, 0),
        YEAR_END,
        weeks=CrewTrack(crews, 1),
    )
    assert capacity == 6.5 * 2 * 2  # 1/4・1/5 の 2 日 × 2 人 × 6.5h(12/30〜1/3 は休み)


def test_leap_day_is_a_working_day_only_in_a_leap_year() -> None:
    # 2028 は閏年: 2/28(月)の翌日 2/29(火)が稼働日。2027 は 2/28(日)の翌日 3/1(月)
    leap = datetime(2028, 2, 21, 9)
    plain = datetime(2027, 2, 22, 9)
    on_29 = end_of(120.0, joining(date(2028, 2, 29), leap), NONE, leap)
    on_mar1 = end_of(120.0, joining(date(2028, 3, 1), leap), NONE, leap)
    assert on_29 < on_mar1  # 2/29 から効くほうが早い
    sunday = end_of(120.0, joining(date(2027, 2, 28), plain), NONE, plain)
    monday = end_of(120.0, joining(date(2027, 3, 1), plain), NONE, plain)
    assert sunday == monday  # 日曜は誰も稼働しない


def test_week_index_counts_calendar_days_across_a_leap_day() -> None:
    # 閏年: 2/26 から 3/3 は 6 日、3/4 は 7 日。平年: 2/26 から 3/4 は 6 日、3/5 は 7 日
    assert week_index(date(2028, 2, 26), date(2028, 3, 3), 9) == 0
    assert week_index(date(2028, 2, 26), date(2028, 3, 4), 9) == 1
    assert week_index(date(2027, 2, 26), date(2027, 3, 4), 9) == 0
    assert week_index(date(2027, 2, 26), date(2027, 3, 5), 9) == 1
    assert week_index(date(2028, 2, 26), date(2028, 3, 4), 9, 1) == 7
    assert week_index(date(2027, 2, 26), date(2027, 3, 5), 9, 1) == 7


# --- 増員する人の個人の休み ----------------------------------------------------


def off(*days: date) -> Worker:
    return Worker(1.0, work_day_map([WorkDay(d) for d in days]), "鈴木")


def test_a_person_who_is_off_adds_nothing_on_their_days_off() -> None:
    # 鈴木は 11/4・11/5 が個人の休み。11/4 から加わっても、効き始めは 11/6
    off_b = off(date(2026, 11, 4), date(2026, 11, 5))
    from_4 = CrewTrack([[A]] * 2 + [[A, off_b]] * 400, 1)
    from_6 = CrewTrack([[A]] * 4 + [[A, off_b]] * 400, 1)
    assert end_of(60.0, from_4) == end_of(60.0, from_6)
    always = CrewTrack([[A]] * 2 + [[A, B]] * 400, 1)
    assert end_of(60.0, always) < end_of(60.0, from_4)


def test_the_others_are_not_affected_by_a_person_off() -> None:
    solo = CrewTrack([[A]] * 400, 1)
    with_off = CrewTrack([[A, off(date(2026, 11, 3))]] * 400, 1)
    stop = datetime(2026, 11, 3, 23)
    assert (
        work_capacity(START, stop, 6.5, time(9, 0), NONE, weeks=with_off)
        == work_capacity(START, stop, 6.5, time(9, 0), NONE, weeks=solo) + 6.5
    )


def test_no_one_working_on_a_day_means_no_progress_that_day() -> None:
    both_off = CrewTrack([[off(date(2026, 11, 3))]] * 400, 1)
    assert end_of(6.5, both_off) == datetime(2026, 11, 2, 15, 30)  # 月曜で終わる
    assert end_of(13.0, both_off) == datetime(2026, 11, 4, 15, 30)  # 火曜(休み)を飛ばす


def test_working_on_a_normally_closed_day_counts_extra_capacity() -> None:
    sat = date(2026, 11, 7)
    weekend = Worker(1.0, work_day_map([WorkDay(sat, time(9, 0), time(17, 0))]), "鈴木")
    days = [[A]] * 5 + [[A, weekend]] + [[A]]
    capacity = work_capacity(
        START, datetime(2026, 11, 8), 6.5, time(9, 0), NONE, weeks=CrewTrack(days, 1)
    )
    assert capacity > 6.5 * 5  # 土曜に鈴木が稼働する


def test_consumed_slices_name_the_working_people_per_day() -> None:
    slices = consumed_slices(
        START, 13.0, 6.5, time(9, 0), NONE, weeks=CrewTrack([[A]] + [[A, B]] * 6, 1)
    )
    assert [sorted(w.name for w in s[2]) for s in slices] == [
        ["田中"],
        ["田中", "鈴木"],
    ]


def test_crew_track_expands_weeks_to_days_only_when_there_is_a_daily_week() -> None:
    weekly = [[Assignee("田中")], [Assignee("田中"), Assignee("鈴木")]]

    def workers(crew):
        return [Worker(1.0, {}, a.name) for a in crew]

    plain = crew_track(weekly, {}, workers)
    assert plain.step == 7 and len(plain) == 2
    mixed = crew_track(weekly, {0: [[Assignee("田中")]] * 7}, workers)
    assert mixed.step == 1 and len(mixed) == 7 + 7
