"""日ごとの担当(要望 135)。NiceGUI に依存しない純粋関数。

週ごとの担当(`Task.weekly_crew`。実効の開始の日から 7 日ごと)のうち、選んだ週だけを日ごとにできる
(`Task.daily_crew`)。日の位置は、起点との暦日の差だけで数える(月・年・閏年で場合分けしない)。
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta

from projectapp.models import MAX_WEEKS, Assignee, Task, union_assignees

WEEK_DAYS = 7
DailyCrew = dict[int, list[list[Assignee]]]


def copy_crew(crew: list[Assignee]) -> list[Assignee]:
    return [replace(a) for a in crew]


def copy_weekly(weekly: list[list[Assignee]]) -> list[list[Assignee]]:
    return [copy_crew(week) for week in weekly]


def copy_daily(daily: DailyCrew) -> DailyCrew:
    return {week: [copy_crew(day) for day in days] for week, days in daily.items()}


def rows_of(task: Task) -> tuple[list[list[Assignee]], DailyCrew]:
    """タスクの週ごとの担当と日ごとの担当の複製。週ごとでないタスクは、担当 1 週ぶん(日ごとなし)。"""
    if not task.weekly_crew:
        return [copy_crew(task.assignees)], {}
    return copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)


def _is_daily(daily: DailyCrew, week: int) -> bool:
    days = daily.get(week)
    return days is not None and len(days) == WEEK_DAYS


def crew_spans(
    weekly: list[list[Assignee]], daily: DailyCrew
) -> list[tuple[int, list[Assignee]]]:
    """(日数, 担当) の並び。週は (7, 担当)、日ごとの週は (1, 担当) × 7。最後の要素は以降も続く。
    週の数を超える添字・7 日でない日ごとの担当は無視する。"""
    spans: list[tuple[int, list[Assignee]]] = []
    for number, week in enumerate(weekly):
        if _is_daily(daily, number):
            spans.extend((1, day) for day in daily[number])
        else:
            spans.append((WEEK_DAYS, week))
    return spans


def _tail(weekly: list[list[Assignee]], daily: DailyCrew) -> list[Assignee]:
    """最後の週の、以降も続く担当(最後の週が日ごとなら、その 7 日目)。"""
    last = len(weekly) - 1
    return daily[last][-1] if _is_daily(daily, last) else weekly[last]


def _plus(crew: list[Assignee], names: tuple[str, ...]) -> list[Assignee]:
    present = {a.name for a in crew}
    return copy_crew(crew) + [Assignee(n) for n in names if n not in present]


def with_added_from(
    weekly: list[list[Assignee]],
    daily: DailyCrew,
    offset: int,
    names: tuple[str, ...],
) -> tuple[list[list[Assignee]], DailyCrew] | None:
    """週の起点から offset 日目(負は 0)以降に names を足した、週ごとの担当と日ごとの担当。
    offset が週頭(7 の倍数)なら日ごとにせず、その週以降の担当に足す。週の途中なら、その週だけを日ごとにする。
    定義済みの最後の週より先は、直前の担当のコピーで間を埋める。52 週以上になるなら None。入力は変えない。"""
    offset = max(offset, 0)
    week, day = divmod(offset, WEEK_DAYS)
    if week >= MAX_WEEKS:
        return None
    rows = copy_weekly(weekly)
    days_by_week = copy_daily(daily)
    while len(rows) <= week:
        rows.append(copy_crew(_tail(rows, days_by_week)))
    for number in range(week, len(rows)):
        first = day if number == week else 0
        if first == 0 and not _is_daily(days_by_week, number):
            rows[number] = _plus(rows[number], names)
            continue
        days = (
            days_by_week[number]
            if _is_daily(days_by_week, number)
            else [copy_crew(rows[number]) for _ in range(WEEK_DAYS)]
        )
        days = [d if i < first else _plus(d, names) for i, d in enumerate(days)]
        days_by_week[number] = days
        rows[number] = union_assignees(days)
    return rows, days_by_week


@dataclass(frozen=True)
class Segment:
    """棒の上のチップ 1 つぶん。週(day が None)か、日ごとの週の 1 日。"""

    week: int  # 0 始まりの週
    day: int | None  # 日ごとの週の 0〜6。週のままは None
    first: date
    last: date  # この区間の最後の日(含む)
    crew: list[Assignee]
    carried: bool  # 定義済みの週より後(最後の担当が続く)


def segments(
    weekly: list[list[Assignee]], daily: DailyCrew, start: date, last_day: date
) -> list[Segment]:
    """start から last_day(含む)までの表示区間。週は 7 日ぶんで 1 つ、日ごとの週は 1 日ずつ。"""
    result: list[Segment] = []
    number = 0
    while (first := start + timedelta(days=WEEK_DAYS * number)) <= last_day:
        if number < len(weekly) and _is_daily(daily, number):
            for j, crew in enumerate(daily[number]):
                day = first + timedelta(days=j)
                if day > last_day:
                    break
                result.append(Segment(number, j, day, day, crew, False))
        else:
            defined = number < len(weekly)
            crew = weekly[number] if defined else _tail(weekly, daily)
            last = first + timedelta(days=WEEK_DAYS - 1)
            result.append(Segment(number, None, first, last, crew, not defined))
        number += 1
    return result


def split_week(task: Task, week: int) -> Task | None:
    """週を日ごとに分ける(その週の担当を 7 日すべてにコピー)。週ごとでない・上限超え・すでに日ごとは None。
    定義済みの最後の週より先なら、直前の担当のコピーで間を埋める。"""
    if not task.weekly_crew or not 0 <= week < MAX_WEEKS:
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    while len(weekly) <= week:
        weekly.append(copy_crew(_tail(weekly, daily)))
    if _is_daily(daily, week):
        return None
    daily[week] = [copy_crew(weekly[week]) for _ in range(WEEK_DAYS)]
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def merge_week(task: Task, week: int) -> Task | None:
    """日ごとの週を週に戻す(1 日目の担当を週の担当にする)。日ごとでなければ None。"""
    if not _is_daily(task.daily_crew, week) or week >= len(task.weekly_crew):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    weekly[week] = copy_crew(daily.pop(week)[0])
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )


def set_week_days(task: Task, week: int, days: list[list[Assignee]]) -> Task | None:
    """日ごとの週の 7 日ぶんの担当を差し替える。日ごとでない週・7 日でない・担当のいない日は None。"""
    if (
        not _is_daily(task.daily_crew, week)
        or week >= len(task.weekly_crew)
        or len(days) != WEEK_DAYS
        or not all(days)
    ):
        return None
    weekly, daily = copy_weekly(task.weekly_crew), copy_daily(task.daily_crew)
    daily[week] = [copy_crew(day) for day in days]
    weekly[week] = union_assignees(daily[week])
    return replace(
        task, weekly_crew=weekly, daily_crew=daily, assignees=union_assignees(weekly)
    )
